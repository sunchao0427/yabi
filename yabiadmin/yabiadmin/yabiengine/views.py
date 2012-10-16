# -*- coding: utf-8 -*-
### BEGIN COPYRIGHT ###
#
# (C) Copyright 2011, Centre for Comparative Genomics, Murdoch University.
# All rights reserved.
#
# This product includes software developed at the Centre for Comparative Genomics 
# (http://ccg.murdoch.edu.au/).
# 
# TO THE EXTENT PERMITTED BY APPLICABLE LAWS, YABI IS PROVIDED TO YOU "AS IS," 
# WITHOUT WARRANTY. THERE IS NO WARRANTY FOR YABI, EITHER EXPRESSED OR IMPLIED, 
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND 
# FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT OF THIRD PARTY RIGHTS. 
# THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF YABI IS WITH YOU.  SHOULD 
# YABI PROVE DEFECTIVE, YOU ASSUME THE COST OF ALL NECESSARY SERVICING, REPAIR
# OR CORRECTION.
# 
# TO THE EXTENT PERMITTED BY APPLICABLE LAWS, OR AS OTHERWISE AGREED TO IN 
# WRITING NO COPYRIGHT HOLDER IN YABI, OR ANY OTHER PARTY WHO MAY MODIFY AND/OR 
# REDISTRIBUTE YABI AS PERMITTED IN WRITING, BE LIABLE TO YOU FOR DAMAGES, INCLUDING 
# ANY GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE 
# USE OR INABILITY TO USE YABI (INCLUDING BUT NOT LIMITED TO LOSS OF DATA OR 
# DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD PARTIES 
# OR A FAILURE OF YABI TO OPERATE WITH ANY OTHER PROGRAMS), EVEN IF SUCH HOLDER 
# OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.
# 
### END COPYRIGHT ###
# -*- coding: utf-8 -*-
from datetime import datetime
from django.http import HttpResponse, HttpResponseNotFound, HttpResponseServerError
from django.shortcuts import render_to_response, get_object_or_404
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.core import urlresolvers
from django.db import transaction 
from django.utils import simplejson as json
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings
from ccg.utils import webhelpers
from yabiadmin.utils import detect_rdbms
from yabiadmin.yabiengine.tasks import walk
from yabiadmin.yabiengine.models import Task, Job, Workflow, Syslog
from yabiadmin.yabiengine.enginemodels import EngineTask, EngineJob, EngineWorkflow
from yabiadmin.yabi.models import BackendCredential

import logging
logger = logging.getLogger(__name__)

from yabiadmin.constants import *
from random import shuffle

def request_next_task(request, status):
    if "tasktag" not in request.REQUEST:
        return HttpResponseServerError("Error requesting task. No tasktag identifier set.")
    
    # verify that the requesters tasktag is correct
    tasktag = request.REQUEST["tasktag"]
    if tasktag != settings.TASKTAG:
        logger.critical("Task requested  had incorrect identifier set. Expected tasktag %s but got %s instead." % (settings.TASKTAG, tasktag))
        return HttpResponseServerError("Error requesting task. Tasktag incorrect. This is not the admin you are looking for.")
    
    # we assemble a list of backendcredentials. This way we can rate control the jobs a particular backend user and backend sees to
    # prevent overload of the scheduler, which is what a job scheduler should deal with, with something like, you know, a queue. but most of them
    # don't. cause they're mostly rubbish.
    backend_user_pairs = [bec for bec in BackendCredential.objects.all()]
    
    # we shuffle this list to try to prevent any starvation of later backend/user pairs
    shuffle(backend_user_pairs)
    
    # for each backend/user pair, we count how many submitted jobs there are. Those with no bec setting are always done first.
    # this enables us later to allow a backend task to be submitted no matter what the remote backend is doing, simply by leaving the column null
    for bec in [None]+backend_user_pairs:
        # the following collects the list of tasks for this bec that are already running on the remote
        #logger.warning("bec: %s tasktag: %s"%(str(bec),str(tasktag)))
        remote_task_candidates = Task.objects.filter(execution_backend_credential=bec).filter(tasktag=tasktag).exclude(job__workflow__status=STATUS_ERROR).exclude(job__workflow__status=STATUS_EXEC_ERROR).exclude(job__workflow__status=STATUS_COMPLETE)
        #logger.warning("candidates: %s"%(str(remote_task_candidates)))
        
        remote_tasks = []
        for n,t in enumerate(remote_task_candidates):
            s = t.status
            #logger.warning("status for %d is: %s"%(n,status))
            if s not in [STATUS_READY, STATUS_ERROR, STATUS_EXEC_ERROR, STATUS_COMPLETE]:
                remote_tasks.append(t)
        
        #logger.warning("remote_tasks: %s"%(str(remote_tasks)))
        
        tasks_per_user = None if not bec or bec.backend.tasks_per_user==None else bec.backend.tasks_per_user
        
        #logger.debug("%d remote tasks running for this bec (%s)"%(len(remote_tasks),bec))
        #logger.debug("tasks_per_user = %s\n"%(tasks_per_user))
        
        if tasks_per_user==None or len(remote_tasks) < tasks_per_user:
            # we can return a task for this bec if one exists
            try:
                tasks = [T for T in Task.objects.filter(execution_backend_credential=bec).filter(tasktag=tasktag) if T.status==status]
                
                #logger.warning("FOUND %s: (%d tasks) %s"%(status,len(tasks),tasks))
                
                # Optimistic locking
                # Update and return task only if another thread hasn't updated and returned it before us
                for task in tasks:
                    updated = Task.objects.filter(id=task.id,status_requested__isnull=True).update(status_requested=datetime.now())
                    if updated == 1:
                        logger.debug('requested %s task id: %s command: %s' % (status, task.id, task.command))
                        return HttpResponse(task.json())

            except ObjectDoesNotExist:
                # this bec has no jobs... continue to try the next one...
                #logger.warning("ODNE")
                pass
            
    logger.debug("No more tasks.")
    return HttpResponseNotFound("No more tasks.")

def task(request):
    return request_next_task(request, status=STATUS_READY)

def blockedtask(request):
    return request_next_task(request, status=STATUS_RESUME)

def status(request, model, id):
    logger.debug('model: %s id: %s method: %s' % (model, id, request.method))
    models = {'task':EngineTask, 'job':EngineJob, 'workflow':EngineWorkflow}

    # sanity checks
    if model.lower() not in models.keys():
        raise ObjectDoesNotExist()

    if request.method == "GET":
        try:
            m = models[model.lower()]
            obj = m.objects.get(id=id)
            return HttpResponse(json.dumps({"status":obj.status}))
        except ObjectDoesNotExist, e:
            return HttpResponseNotFound("Object not found")
    elif request.method == "POST":
        if "status" not in request.POST:
            return HttpResponseServerError("POST request to status service should contain 'status' parameter\n")

        try:
            model = str(model).lower()
            id = int(id)
            status = str(request.POST["status"])

            if model != "task":
                return HttpResponseServerError("Only the status of Tasks is allowed to be changed\n")

            logger.debug("task id: %s status=%s" % (id, request.POST['status']))

            # TODO TSZ maybe raise exception instead?
            # truncate status to 64 chars to avoid any sql field length errors
            status = status[:64]
            task = EngineTask.objects.get(pk=id)
        except (ObjectDoesNotExist,ValueError):
            return HttpResponseNotFound("Object not found")

        try:
            update_task_status(task.pk, status)
        except Exception, e:
            return HttpResponseServerError(e)

        return HttpResponse("")

@transaction.commit_manually
def update_task_status(task_id, status):
    #logger.warning("Entry update_task_status %d with status %s"%(task_id,status))
    try:
        def log_ignored():
            logger.warning('Ignoring status update of task %s from %s to %s' % (task.pk, task.status, status))

        #logger.warning("task: %d updating to: %s"%(task_id,status))

        #logger.warning("task: %d updating.status to: %s"%(task_id,status))
        #task.status = status
        kwargs = {Task.status_attr(status): datetime.now()}
        Task.objects.filter(id=task_id).update(**kwargs)
        task = Task.objects.get(id=task_id)

        if status != STATUS_BLOCKED and status!= STATUS_RESUME:
            task.percent_complete = STATUS_PROGRESS_MAP[status]

        if status == STATUS_COMPLETE:
            task.end_time = datetime.now()
        
        #logger.warning("task: %d updating to: %s presave"%(task_id,status))
        task.save()
        #logger.warning("task: %d updating to: %s postsave"%(task_id,status))
       
        # We have to commit the task status before calculating
        # job status that is based on task statuses
        transaction.commit()
 
        # update the job status when the task status changes
        task.job.update_status()
        job_cur_status = task.job.status

        #logger.warning("task: %d updating to: %s precommit"%(task_id,status))
        transaction.commit()
        #logger.warning("task: %d updating to: %s postcommit"%(task_id,status))
        
        if job_cur_status in [STATUS_READY, STATUS_COMPLETE, STATUS_ERROR]:
            workflow = EngineWorkflow.objects.get(pk=task.job.workflow.id)
            if workflow.needs_walking():
                # trigger a walk via celery 
                walk.delay(workflow_id=workflow.pk)
        transaction.commit()
    except Exception, e:
        transaction.rollback()
        import traceback
        logger.critical(traceback.format_exc())
        logger.critical("Caught Exception: %s" % e)
        raise

def remote_id(request,id):
    logger.debug('remote_task_id> %s'%id)
    try:
        if "remote_id" not in request.POST:
            return HttpResponseServerError("POST request to remote_id service should contain 'remote_id' parameter\n")

        id = int(id)
        remote_id = str(request.POST["remote_id"])

        logger.debug("remote_id="+request.POST['remote_id'])

        # truncate status to 256 chars to avoid any sql field length errors
        remote_id = remote_id[:256]

        obj = EngineTask.objects.get(id=id)
        obj.remote_id = remote_id
        obj.save()

        return HttpResponse("")
    except (ObjectDoesNotExist,ValueError):
        return HttpResponseNotFound("Object not found")
    except Exception, e:
        import traceback
        logger.critical(traceback.format_exc())
        logger.critical("Caught Exception: %s" % e)
        return HttpResponseServerError(e)

def remote_info(request,id):
    logger.debug('remote_task_info> %s'%id)
    try:
        if "remote_info" not in request.POST:
            return HttpResponseServerError("POST request to remote_info service should contain 'remote_info' parameter\n")

        id = int(id)
        remote_info = str(request.POST["remote_info"])

        logger.debug("remote_info="+request.POST['remote_info'])

        # truncate status to 2048 chars to avoid any sql field length errors
        remote_info = remote_info[:2048]

        obj = EngineTask.objects.get(id=id)
        obj.remote_info = remote_info
        obj.save()

        return HttpResponse("")
    except (ObjectDoesNotExist,ValueError):
        return HttpResponseNotFound("Object not found")
    except Exception, e:
        import traceback
        logger.critical(traceback.format_exc())
        logger.critical("Caught Exception: %s" % e)
        return HttpResponseServerError(e)

def error(request, table, id):
    logger.debug('table: %s id: %s' % (table, id))
    
    try:

        if request.method == "GET":
            entries = Syslog.objects.filter(table_name=table, table_id=id)

            if not entries:
                raise ObjectDoesNotExist()

            output = [{"table_name":x.table_name, "table_id":x.table_id, "message":x.message} for x in entries]
            return HttpResponse(json.dumps(output))

        else:

            # check we have required params
            if "message" not in request.POST:
                return HttpResponseServerError("POST request to error service should contain 'message' parameter\n")

            syslog = Syslog(table_name=str(table),
                            table_id=int(id),
                            message=str(request.POST["message"])
                            )

            syslog.save()

            return HttpResponse("Thanks!")

    except (ObjectDoesNotExist,ValueError):
        return HttpResponseNotFound("Object not found")
    except Exception, e:
        logger.critical("Caught Exception: %s" % e.message)
        return HttpResponseNotFound("Object not found")


def job(request, workflow, order):
    try:
        workflow = EngineWorkflow.objects.get(id=int(workflow))
        job = EngineJob.objects.get(workflow=workflow, order=int(order))

        # Put some fields of general interest in.
        output = {
            "id": job.id,
            "status": job.status,
            "tasks": [],
        }

        for task in job.task_set.all():
            try:
                remote_info = json.loads(task.remote_info)
            except (TypeError, ValueError):
                # JSON failed to decode or was null.
                remote_info = None

            output["tasks"].append({
                "id": task.id,
                "percent_complete": task.percent_complete,
                "remote_id": task.remote_id,
                "remote_info": remote_info,
            })

        return HttpResponse(json.dumps(output), mimetype="application/json")
    except (MultipleObjectsReturned, ObjectDoesNotExist, ValueError):
        return HttpResponseNotFound("Object not found")
    except Exception, e:
        logger.critical("Caught Exception: %s" % e.message)
        return HttpResponseNotFound("Object not found")


@staff_member_required
def task_json(request, task):
    logger.debug("task_json> %s" % task)

    try:
        task = Task.objects.get(id=int(task))
        return HttpResponse(content=task.json(), content_type="application/json; charset=UTF-8")
    except (ObjectDoesNotExist, ValueError):
        return HttpResponseNotFound("Task not found")


@staff_member_required
def workflow_summary(request, workflow_id):
    logger.debug('')

    workflow = get_object_or_404(EngineWorkflow, pk=workflow_id)
   
    return render_to_response('yabiengine/workflow_summary.html', {
        'w': workflow,
        'user':request.user,
        'title': 'Workflow Summary',
        'root_path':urlresolvers.reverse('admin:index'),
        'settings':settings
        })
