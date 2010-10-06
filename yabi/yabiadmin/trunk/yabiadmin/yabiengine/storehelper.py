# -*- coding: utf-8 -*-
import httplib, os
import uuid
from urllib import urlencode
from os.path import splitext

from django.conf import settings
from django.utils import simplejson as json

from yabiadmin.yabistoreapp import db

import logging
logger = logging.getLogger('yabiengine')


def updateWorkflow(workflow, workflow_json=None):
    if workflow_json is None:
        return 200,db.get_workflow( workflow.user.name, workflow.id )

    updateset = {'json':workflow_json,
                 'name':workflow.name,
                 'status':workflow.status
                 }

    #dont update the taglist with this set
    return 200,db.update_workflow( workflow.user.name, workflow.id, updateset )

def getWorkflow(workflow):
    ''' Get the JSON for the given workflow
    '''
    print "getWorkflow",workflow
    return db.get_workflow(workflow.user.name,workflow.id)

def updateJob(job, snippet={}):
    ''' Within a workflow, update a job snippet of the form:
            {'tasksComplete':1.0,
                'tasksTotal':1.0
            }

        Also does status & stageout from the job
    '''
    print "updateJob",job,snippet
    # get the workflow that needs updating
    json_object = getWorkflow(job.workflow)

    job_id = int(job.order)
    assert json_object['json']['jobs'][job_id]['jobId'] == job_id + 1 # jobs are 1 indexed in json

    # status
    json_object['json']['jobs'][job_id]['status'] = job.status

    # data
    for key in snippet:
        json_object['json']['jobs'][job_id][key] = snippet[key]

    # stageout
    if job.stageout:
        json_object['json']['jobs'][job_id]['stageout'] = job.stageout

    # save the workflow json in the store
    updateWorkflow(job.workflow, json.dumps(json_object['json']))

def deleteWorkflow(workflow):
    ''' Delete all references to a workflow from the store.
    '''
    print "deleteWorkflow",workflow
    logger.debug('')
    resource = os.path.join(settings.YABISTORE_BASE,"workflows/delete", workflow.user.name, str(workflow.id))
    conn = httplib.HTTPConnection(settings.YABISTORE_SERVER)
    conn.request('GET', resource)
    logger.debug("store get: %s" % resource)
    r = conn.getresponse()
    status = r.status
    data = r.read()
    logger.debug("store get: %s" % status)
    return status,data
