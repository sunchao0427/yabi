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
import mimetypes
import uuid
import os
import re

from datetime import datetime, timedelta
from urllib import quote
from urlparse import urlparse, urlunparse

from django.http import HttpResponse, HttpResponseNotFound, HttpResponseForbidden, HttpResponseBadRequest, HttpResponseNotAllowed, HttpResponseServerError, Http404
from django.shortcuts import render_to_response, get_object_or_404
from django.core.exceptions import ObjectDoesNotExist
from yabiadmin.yabi.models import User, ToolGrouping, ToolGroup, Tool, ToolParameter, Credential, Backend, ToolSet, BackendCredential
from yabiadmin.yabi.models import DecryptedCredentialNotAvailable
from django.utils import webhelpers
from django.utils import simplejson as json
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.ldap_helper import LDAPSearchResult, LDAPHandler
from django.conf import settings

from crypto import DecryptException

from yabiadmin.yabiengine import storehelper as StoreHelper
from yabiadmin.yabiengine.tasks import build
from yabiadmin.yabiengine.enginemodels import EngineWorkflow
from yabiadmin.yabiengine.models import WorkflowTag
from yabiadmin.yabiengine.backendhelper import get_listing, get_backend_list, get_file, get_backendcredential_for_uri, copy_file, rm_file, send_upload_hash
from yabiadmin.responses import *
from yabi.file_upload import *
from django.contrib import auth
from yabiadmin.decorators import memcache, authentication_required

from yabiadmin.yabistoreapp import db

import logging
logger = logging.getLogger('yabiadmin')

from UploadStreamer import UploadStreamer

DATE_FORMAT = '%Y-%m-%d'

class FileUploadStreamer(UploadStreamer):
    def __init__(self, host, port, selector, cookies, fields):
        UploadStreamer.__init__(self)
        self._host = host
        self._port = port
        self._selector = selector
        self._fields = fields
        self._cookies = cookies
    
    def receive_data_chunk(self, raw_data, start):
        #print "receive_data_chunk", len(raw_data), start
        return self.file_data(raw_data)
    
    def file_complete(self, file_size):
        """individual file upload complete"""
        #print "file_complete",file_size
        return self.end_file()
    
    def new_file(self, field_name, file_name, content_type, content_length, charset):
        """beginning of new file in upload"""
        #print "new_file",field_name, file_name, content_type, content_length, charset
        return UploadStreamer.new_file(self,file_name)
    
    def upload_complete(self):
        """all files completely uploaded"""
        #print "upload_complete"
        return self.end_connection()
    
    def handle_raw_input(self, input_data, META, content_length, boundary, encoding, chunked):
        """raw input"""
        # this is called right at the beginning. So we grab the uri detail here and initialise the outgoing POST
        self.post_multipart(host=self._host, port=self._port, selector=self._selector, cookies=self._cookies )
   

## TODO do we want to limit tools to those the user can access?
## will need to change call from front end to include username
## then uncomment decorator


def ensure_encrypted(username, password):
    """returns true on successful encryption. false on failure to decrypt"""
    # find the unencrypted credentials for this user that should be ecrypted and encrypt with the passed in CORRECT password
    creds = Credential.objects.filter(user__name=username).filter(encrypt_on_login=True).filter(encrypted=False)
    for cred in creds:
        cred.encrypt(password)
        cred.save()
        
    # decrypt all encrypted credentials and store in memcache
    creds = Credential.objects.filter(user__name=username, encrypted=True)
    try:
        for cred in creds:
            cred.send_to_memcache(password)
    except DecryptException, de:
        return False

    return True                 #success

def login(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    username = request.POST.get('username')
    password = request.POST.get('password')
    if not (username and password):
        return HttpResponseBadRequest()
    user = auth.authenticate(username=username, password=password)
    if user is not None:
        if user.is_active:
            auth.login(request, user)
            response = {
                "success": True
            }
            
            # encrypt any pending user credentials.
            if not ensure_encrypted(user.username,password):
                response = {
                    "success": False,
                    "message": "One or more of the credentials failed to decrypt with your password. Please see your system administrator."
                }
        else:
            response = {
                "success": False,
                "message": "The account has been disabled.",
            }
    else:
        response = {
            "success": False,
            "message": "The user name and password are incorrect.",
        }
        
    return HttpResponse(content=json.dumps(response))

def logout(request):
    auth.logout(request)
    response = {
        "success": True,
    }
    return HttpResponse(content=json.dumps(response))

@authentication_required
@memcache("tool",timeout=30,refresh=True,request_specific=False,user_specific=False)                # global app tool cache
def tool(request, toolname):
    logger.debug(toolname)

    try:
        tool = Tool.objects.get( name=toolname )
        return HttpResponse(tool.json_pretty(), content_type="text/plain; charset=UTF-8")
    except ObjectDoesNotExist:
        return JsonMessageResponseNotFound("Object not found")



@authentication_required
@memcache("menu",timeout=300)
def menu(request):
    username = request.user.username
    logger.debug('Username: ' + username)

    try:
        all_tools = {}
        toolsets = ToolSet.objects.filter(users__name=username)
        for toolset in toolsets:
            for toolgroup in ToolGrouping.objects.filter(tool_set=toolset):
                tg = all_tools.setdefault(toolgroup.tool_group.name, {})
                tool = tg.setdefault(toolgroup.tool.name, {})
                if not tool:
                    tool["name"] = toolgroup.tool.name
                    tool["displayName"] = toolgroup.tool.display_name
                    tool["description"] = toolgroup.tool.description                
                    tool["outputExtensions"] = toolgroup.tool.output_filetype_extensions()
                    tool["inputExtensions"] = toolgroup.tool.input_filetype_extensions()


        # from here down is getting the tools into a form
        # used by the front end so no changes are needed there
        # toolsets are dev, marine science, ccg etc, not used on the front end
        # toolgroups are for example genomics, select data, mapreduce        

        output = {}
        output['menu'] = {}
        output['menu']['toolsets'] = []

        all_tools_toolset = {}
        output['menu']['toolsets'].append(all_tools_toolset)

        all_tools_toolset["name"] = 'all_tools'
        all_tools_toolset["toolgroups"] = []


        for key, toolgroup in all_tools.iteritems():
            tg = {}
            tg['name'] = key
            tg['tools'] = []

            for toolname, tool in toolgroup.iteritems():
                tg['tools'].append(tool)

            all_tools_toolset["toolgroups"].append(tg)

        return HttpResponse(json.dumps(output))
    except ObjectDoesNotExist:
        return JsonMessageResponseNotFound("Object not found")

@authentication_required
def ls(request):
    """
    This function will return a list of backends the user has access to IF the uri is empty. If the uri
    is not empty then it will pass on the call to the backend to get a listing of that uri
    """
    yabiusername = request.user.username

    try:
        logger.debug("yabiusername: %s uri: %s" %(yabiusername, request.GET['uri']))
        if request.GET['uri']:
            recurse = request.GET.get('recurse')
            filelisting = get_listing(yabiusername, request.GET['uri'], recurse is not None)
        else:
            filelisting = get_backend_list(yabiusername)

        return HttpResponse(filelisting)
    except DecryptedCredentialNotAvailable, dcna:
        return JsonMessageResponseServerError(dcna)
    except AssertionError, e:
        # The file handling functions in the backendhelper module throw
        # assertion errors when they receive an unexpected HTTP status code
        # from the backend. Since failed assertions don't result in the
        # exception having a useful message, we'll intercept it here and return
        # a response with something a little more useful for the user.
        return JsonMessageResponseNotFound("The requested directory either doesn't exist or is inaccessible")
    except Exception, e:
        return JsonMessageResponseNotFound(e)


@authentication_required
def copy(request):
    """
    This function will instantiate a copy on the backend for this user
    """
    yabiusername = request.user.username
    try:
        # TODO: This needs to be fixed in the FRONTEND, by sending the right url through as destination. For now we just make sure it ends in a slash
        src,dst = request.GET['src'],request.GET['dst']
        if dst[-1]!='/':
            dst += '/'
        logger.debug("yabiusername: %s src: %s -> dst: %s" %(yabiusername, src, dst))
        
        status, data = copy_file(yabiusername,src,dst)

        return HttpResponse(content=data, status=status)
    except AssertionError, e:
        # The file handling functions in the backendhelper module throw
        # assertion errors when they receive an unexpected HTTP status code
        # from the backend. Since failed assertions don't result in the
        # exception having a useful message, we'll intercept it here and return
        # a response with something a little more useful for the user.
        return JsonMessageResponseNotFound("The requested copy operation failed: please check that both the source file and destination exist and are accessible")
    except Exception, e:
        return JsonMessageResponseNotFound(e)

@authentication_required
def rm(request):
    """
    This function will return a list of backends the user has access to IF the uri is empty. If the uri
    is not empty then it will pass on the call to the backend to get a listing of that uri
    """
    yabiusername = request.user.username
    try:
        logger.debug("yabiusername: %s uri: %s" %(yabiusername, request.GET['uri']))
        status, data = rm_file(yabiusername,request.GET['uri'])

        return HttpResponse(content=data, status=status)
    except AssertionError, e:
        # The file handling functions in the backendhelper module throw
        # assertion errors when they receive an unexpected HTTP status code
        # from the backend. Since failed assertions don't result in the
        # exception having a useful message, we'll intercept it here and return
        # a response with something a little more useful for the user.
        return JsonMessageResponseNotFound("The requested file or directory is inaccessible and cannot be deleted")
    except Exception, e:
        return JsonMessageResponseNotFound(e)


@authentication_required
def get(request):
    """
    Returns the requested uri. get_file returns an httplib response wrapped in a FileIterWrapper. This can then be read
    by HttpResponse
    """
    yabiusername = request.user.username
    try:
        logger.debug("yabiusername: %s uri: %s" %(yabiusername, request.GET['uri']))
        uri = request.GET['uri']
        
        try:
            filename = uri.rsplit('/', 1)[1]
        except IndexError, e:
            logger.critical('Unable to get filename from uri: %s' % uri)
            filename = 'default.txt'

        bytes = request.GET.get("bytes", None)
        if bytes is not None:
            try:
                bytes = int(bytes)
            except ValueError:
                bytes = None

        response = HttpResponse(get_file(yabiusername, uri, bytes=bytes))

        mimetypes.init([os.path.join(settings.PROJECT_DIRECTORY, 'mime.types')])
        mtype, file_encoding = mimetypes.guess_type(filename, False)
        if mtype is not None:
            response['content-type'] = mtype

        response['content-disposition'] = 'attachment; filename=%s' % filename

        return response

    except Exception, e:
        # The response from this view is displayed directly to the user, so
        # we'll send a normal response rather than a JSON message.
        raise Http404

@authentication_required
def put(request):
    """
    Uploads a file to the supplied URI
    """
    import socket
    import httplib

    yabiusername = request.user.username

    try:
        logger.debug("uri: %s" %(request.GET['uri']))
        uri = request.GET['uri']

        bc = get_backendcredential_for_uri(yabiusername, uri)
        resource = "%s?uri=%s" % (settings.YABIBACKEND_PUT, quote(uri))
        resource += "&username=%s&password=%s&cert=%s&key=%s"%(quote(bc.credential.username),quote(bc.credential.password),quote( bc.credential.cert),quote(bc.credential.key))

        streamer = FileUploadStreamer(host=settings.BACKEND_IP, port=settings.BACKEND_PORT, selector=resource, cookies=[], fields=[])
        request.upload_handlers = [ streamer ]
        
        # evaluating POST triggers the processing of the request body
        request.POST

        result = streamer.stream.getresponse()
        content=result.read()
        status=int(result.status)
        reason = result.reason
        
        return HttpResponse(content=content,status=status)
        
    except socket.error, e:
        logger.critical("Error connecting to %s: %s" % (settings.YABIBACKEND_SERVER, e))
        raise
    except httplib.CannotSendRequest, e:
        logger.critical("Error connecting to %s: %s" % (settings.YABIBACKEND_SERVER, e.message))
        raise

@authentication_required
def submit_workflow(request):
    yabiusername = request.user.username
    logger.debug(yabiusername)

    received_json = request.POST["workflowjson"]
    workflow_dict = json.loads(received_json)
    user = User.objects.get(name=yabiusername)

    # Check if the user already has a workflow with the same name, and if so,
    # munge the name appropriately.
    workflow_dict["name"] = munge_name(yabiusername, workflow_dict["name"])
   
    workflow_json = json.dumps(workflow_dict)
    workflow = EngineWorkflow(name=workflow_dict["name"], user=user, json=workflow_json, original_json=received_json)
    workflow.save()

    # trigger a build via celery
    build.delay(workflow_id=workflow.id)

    return HttpResponse(json.dumps({"id":workflow.id}))

def munge_name(user, workflow_name):
    if EngineWorkflow.objects.filter(user__name=user, name=workflow_name).count() == 0:
        if not db.does_workflow_exist(user, name=workflow_name):
            return workflow_name

    # See if the name has already been munged.
    match = re.search(r"^(.*) \(([0-9]+)\)$", workflow_name)
    if match:
        base = match.group(1)
        val = int(match.group(2))
    else:
        base = workflow_name
        val = 1

    used_names = [wf.name for wf in EngineWorkflow.objects.filter(
                        user__name=user, name__startswith=base)]
    used_names.extend(db.workflow_names_starting_with(user, base))
    used_names = dict(zip(used_names, [None] * len(used_names)))

    munged_name = "%s (%d)" % (base, val)
    while munged_name in used_names:
        val += 1
        munged_name = "%s (%d)" % (base, val)
        
    return munged_name
 
@authentication_required
def get_workflow(request, workflow_id):
    yabiusername = request.user.username
    logger.debug(yabiusername)

    if not (workflow_id and yabiusername):
        return JsonMessageResponseNotFound('No workflow_id or no username supplied')

    workflow_id = int(workflow_id)
    workflows = EngineWorkflow.objects.filter(id=workflow_id)
    if len(workflows) == 1:
        response = workflow_to_response(workflows[0])
    else:
        try:
            response = db.get_workflow(yabiusername,workflow_id)
        except (db.NoSuchWorkflow), e:
            logger.critical('%s' % e)
            return JsonMessageResponseNotFound(e)

    return HttpResponse(json.dumps(response),
                        mimetype='application/json')

def workflow_to_response(workflow, key=None, parse_json=True, retrieve_tags=True):
    fmt = DATE_FORMAT
    response = {
            'id': workflow.id,
            'name': workflow.name,
            'last_modified_on': workflow.last_modified_on.strftime(fmt),
            'created_on': workflow.created_on.strftime(fmt),
            'status': workflow.status,
            'json': json.loads(workflow.json) if parse_json else workflow.json,
            "tags": [],
        } 

    if retrieve_tags:
        response["tags"] = [wft.tag.value for wft in workflow.workflowtag_set.all()] 

    if key is not None:
        response = (getattr(workflow,key), response)

    return response

@authentication_required
def workflow_datesearch(request):
    if request.method != 'GET':
        return JsonMessageResponseNotAllowed(["GET"])

    yabiusername = request.user.username
    logger.debug(yabiusername)

    fmt = DATE_FORMAT
    tomorrow = lambda : datetime.today()+timedelta(days=1)

    start = datetime.strptime(request.GET['start'], fmt)
    end = request.GET.get('end')
    if end is None:
        end = tomorrow()
    else:
        end = datetime.strptime(end, fmt)
    sort = request.GET['sort'] if 'sort' in request.GET else '-created_on'
    sort_dir, sort_field = ('ASC', sort)
    if sort[0] == '-':
        sort_dir, sort_field = ('DESC', sort[1:])
 
    # Retrieve the matched workflows.
    workflows = EngineWorkflow.objects.filter(
           user__name = yabiusername,
           created_on__gte = start, created_on__lte = end
        ).order_by(sort)

    # Use that list to retrieve all of the tags applied to those workflows in
    # one query, then build a dict we can use when iterating over the
    # workflows.
    workflow_tags = WorkflowTag.objects.select_related("tag", "workflow").filter(workflow__in=workflows)
    tags = {}
    for wt in workflow_tags:
        tags[wt.workflow.id] = tags.get(wt.workflow.id, []) + [wt.tag.value]

    response = []
    for workflow in workflows:
        workflow_response = workflow_to_response(workflow, sort_field, parse_json=False, retrieve_tags=False)
        workflow_response[1]["tags"] = tags.get(workflow.id, [])
        response.append(workflow_response)

    archived_workflows = db.find_workflow_by_date(yabiusername,start,end,sort_field,sort_dir)

    response.extend(archived_workflows)
    response.sort(key=lambda x: x[0], reverse=sort_dir=='DESC')
    response = [r[1] for r in response]

    return HttpResponse(json.dumps(response), mimetype='application/json')

@authentication_required
def workflow_change_tags(request, id=None):
    if request.method != 'POST':
        return JsonMessageResponseNotAllowed(["POST"])
    id = int(id)

    yabiusername = request.user.username
    logger.debug(yabiusername)

    if 'taglist' not in request.POST:
        return HttpResponseBadRequest("taglist needs to be passed in\n")
 
    taglist = request.POST['taglist'].split(',')
    taglist = [t.strip() for t in taglist if t.strip()]
    try:
        workflow = EngineWorkflow.objects.get(pk=id)
    except EngineWorkflow.DoesNotExist:
        if db.does_workflow_exist(yabiusername, id=id):
            db.change_workflow_tags(yabiusername, id, taglist)
        else:
            return HttpResponseNotFound()
         
    else:
        workflow.change_tags(taglist)
    return HttpResponse("Success")

#@authentication_required
def getuploadurl(request):
    raise Exception, "test explosion"
    
    if 'uri' not in request.REQUEST:
        return HttpResponseBadRequest("uri needs to be passed in\n")
    
    yabiusername = request.user.username
    uri = request.REQUEST['uri']
    
    uploadhash = str(uuid.uuid4())
        
    # now send this hash to the back end to inform it of the soon to be incomming upload
    upload_url = send_upload_hash(yabiusername,uri,uploadhash)
    
    # at the moment we can just return the URL for the backend upload. Todo. return a hash based URL
    #schema = "http"
    #host = request.META['SERVER_NAME']
    #port = int(request.META['SERVER_PORT'])
    #path = "/fs/put?uri=%s&yabiusername=%s"%(request.REQUEST['uri'], request.REQUEST['yabiusername'])
    
    return HttpResponse(
        json.dumps(upload_url)
    )

@authentication_required
def passchange(request):
    if request.method != "POST":
        return HttpResponseNotAllowed("Method must be POST")
    
    yabiuser = User.objects.get(name=request.user.username)
    oldPassword = request.POST['oldPassword']
    newPassword = request.POST['newPassword']
    
    # get all creds for this user that are encrypted
    creds = Credential.objects.filter(user=yabiuser, encrypted=True)
    for cred in creds:
        cred.recrypt(oldPassword, newPassword)
        cred.save()
        
    return HttpResponse(json.dumps("OK"))
        
@authentication_required
def credential(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    yabiuser = User.objects.get(name=request.user.username)
    creds = Credential.objects.filter(user=yabiuser)

    exists = lambda value: value is not None and len(value) > 0

    def backends(credential):
        backend_credentials = BackendCredential.objects.filter(credential=credential)
        backends = []

        for bc in backend_credentials:
            # Build up the display URI for the backend, which may include the
            # home directory and username in addition to the backend URI
            # proper.
            if bc.homedir:
                uri = bc.backend.uri + bc.homedir
            else:
                uri = bc.backend.uri

            scheme, netloc, path, params, query, fragment = urlparse(uri)

            # Add the credential username if the backend URI doesn't already
            # include one.
            if "@" not in netloc:
                netloc = "%s@%s" % (credential.username, netloc)

            backends.append(urlunparse((scheme, netloc, path, params, query, fragment)))

        return backends

    def expires_in(expires_on):
        if expires_on is not None:
            # Unfortunately, Python's timedelta class doesn't provide a simple way
            # to get the number of seconds total out of it.
            delta = expires_on - datetime.now()
            return (delta.days * 86400) + delta.seconds
        
        return None

    return HttpResponse(json.dumps([{
        "id": c.id,
        "description": c.description,
        "username": c.username,
        "password": exists(c.password),
        "certificate": exists(c.cert),
        "key": exists(c.key),
        "backends": backends(c),
        "expires_in": expires_in(c.expires_on),
        "encrypted": c.encrypted,
    } for c in creds]), content_type="application/json; charset=UTF-8")


@authentication_required
def save_credential(request, id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    try:
        credential = Credential.objects.get(id=id)
        yabiuser = User.objects.get(name=request.user.username)
    except Credential.DoesNotExist:
        return JsonMessageResponseNotFound("Credential ID not found")
    except User.DoesNotExist:
        return JsonMessageResponseNotFound("User not found")

    if credential.user != yabiuser:
        return JsonMessageResponseForbidden("User does not have access to the given credential")

    # Special case: if we're only updating the expiry, we should do that first,
    # since we can do that without unencrypting encrypted credentials.
    if "expiry" in request.POST:
        if request.POST["expiry"] == "never":
            credential.expires_on = None
        else:
            try:
                credential.expires_on = datetime.now() + timedelta(seconds=int(request.POST["expiry"]))
            except TypeError:
                return JsonMessageResponseBadRequest("Invalid expiry")

    # OK, let's see if we have any of password, key or certificate. If so, we
    # replace all of the fields and clear the encrypted flag, since this
    # service can only create unencrypted credentials at present.
    if "password" in request.POST or "key" in request.POST or "certificate" in request.POST:
        credential.encrypted = False
        credential.password = request.POST.get("password", "")
        credential.key = request.POST.get("key", "")
        credential.cert = request.POST.get("certificate", "")

    if "username" in request.POST:
        credential.username = request.POST["username"]

    credential.save()

    return JsonMessageResponse("Credential updated successfully")