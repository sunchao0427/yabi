from twisted.web2 import resource, http_headers, responsecode, http, server
from twisted.internet import defer, reactor
from submit_helpers import parsePOSTDataRemoteWriter
import weakref
import sys, os


class FileMkdirResource(resource.PostableResource):
    VERSION=0.1
    maxMem = 100*1024
    maxFields = 16
    maxSize = 10*1024*102
    
    def __init__(self,request=None, path=None, fsresource=None):
        """Pass in the backends to be served out by this FSResource"""
        self.path = path
        
        if not fsresource:
            raise Exception, "FileMkdirResource must be informed on construction as to which FSResource is its parent"
        
        self.fsresource = weakref.ref(fsresource)
        
    def render(self, request):
        # break our request path into parts
        return http.Response( responsecode.BAD_REQUEST, {'content-type': http_headers.MimeType('text', 'plain')}, "request must be POST\n")

    def http_POST(self, request):
        """
        Respond to a POST request.
        Reads and parses the incoming body data then calls L{render}.
    
        @param request: the request to process.
        @return: an object adaptable to L{iweb.IResponse}.
        
        NOTE: parameters must be Content-Type: application/x-www-form-urlencoded
        eg. 
        """
        print "POST!",request
        
        deferred = parsePOSTDataRemoteWriter( request,
            self.maxMem, self.maxFields, self.maxSize )
        
        client_channel = defer.Deferred()
        
        # Copy command
        def MkdirCommand(res):
            # source and destination
            if 'dir' not in request.args:
                return http.Response( responsecode.BAD_REQUEST, {'content-type': http_headers.MimeType('text', 'plain')}, "copy must specify a directory 'dir' to make\n")
            
            directory = request.args['dir'][0]
           
            path = directory.split("/")
            
            bendname,username,pathremainder = path[0], path[1], path[2:]
            
            # get the backend
            bend = getattr(self.fsresource(), "child_%s"%bendname)
            
            # make the directory. returns a deferred, in which the result will be called down
            mkdir=bend.http_MKDIR(request,path=[username]+pathremainder, username=username)
            
            if isinstance(mkdir,defer.Deferred):
                def _mkdir_done(res):
                    print dir(res)
                    if res.code!=200:
                        client_channel.callback(http.Response( responsecode.INTERNAL_SERVER_ERROR, {'content-type': http_headers.MimeType('text', 'plain')}, "NOT OK: %s\n"%str(res.stream.read())) )
                    else:
                        client_channel.callback(http.Response( responsecode.OK, {'content-type': http_headers.MimeType('text', 'plain')}, stream=res.stream) )
                
                mkdir.addCallback(_mkdir_done)
                mkdir.addErrback( lambda r: client_channel.callback(http.Response( responsecode.INTERNAL_SERVER_ERROR, {'content-type': http_headers.MimeType('text', 'plain')}, "NOT OK: %s\n"%str(r)) ))
            else:
                client_channel.callback(mkdir)
             
        # on success, make the dir
        deferred.addCallback(MkdirCommand)
        
        # save failed
        deferred.addErrback(lambda res: client_channel.callback(http.Response( responsecode.INTERNAL_SERVER_ERROR, {'content-type': http_headers.MimeType('text', 'plain')}, "NOT OK: %s\n"%str(res)) ))
        
        return client_channel
