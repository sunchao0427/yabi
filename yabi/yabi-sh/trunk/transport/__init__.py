
import sys
import urllib, urlparse
import httplib2
import readline
from cookies import CookieJar, FileCookiePersister
import copy
import os

#httplib2.debuglevel = 1

class UnauthorizedError(StandardError):
    pass

DEFAULT_WORKDIR = '.httplib2_workdir'

class Transport(object):
    def __init__(self, workdir=DEFAULT_WORKDIR, base_url='',cache=True, cookie_persister=None):
        self.workdir = workdir
        if cache:
            cache_dir = self.setup_cachedir()
            self.h = httplib2.Http(cache_dir)
        else:
            self.h = httplib2.Http()

        if cookie_persister is None:
            jar_file = os.path.join(self.workdir, 'cookies.txt')
            self.cookie_jar = CookieJar(persister=FileCookiePersister(jar_file))
        else:
            self.cookie_jar = CookieJar(persister=cookie_persister)

        self.base_url = base_url
        if not self.base_url.endswith('/'):
            self.base_url += '/'

    def __enter__(self):
        return self

    def __exit__(self, typ, value, traceback):
        self.finish_session()

    def setup_cachedir(self):
        cachedir = os.path.join(self.workdir, 'cache')
        if not os.path.exists(cachedir):
            os.makedirs(cachedir)
        return cachedir

    def is_relative(self, url):
        pr = urlparse.urlparse(url)
        return pr[0] == '' # empty scheme

    def make_request(self, request):
        req_url = request.url
        if self.is_relative(req_url):
            req_url = self.base_url + req_url
        request.add_headers(self.cookie_jar.cookies_to_send_header(req_url))

        resp, content = self.h.request(req_url, request.method, body=request.body, headers=request.headers)

        # TODO more error handling required here

        if resp.status == 401:
            raise UnauthorizedError()

        self.cookie_jar.update_from_response(resp, req_url)

        return resp, content

    def finish_session(self):
        self.cookie_jar.save()

class Request(object): 
    def __init__(self, method, url, params = None, headers = None):
        self.method = method
        self._url = url
        self._params = params
        self._headers = {} if headers is None else headers
        self._body = None

    @property
    def url(self):
        return self._url

    @property
    def headers(self):
        return self._headers

    def add_headers(self, headers):
        self._headers.update(headers)

    @property
    def body(self):
        return self._body

class GetRequest(Request):
    def __init__(self, url, params=None):
        Request.__init__(self, 'GET', url, params)

    @property
    def url(self):
        return self._url + '?' + urllib.urlencode(self._params)


class PostRequest(Request):
    def __init__(self, url, params=None, headers=None, files=None):
        Request.__init__(self, 'POST', url, params, headers)
        self._files = files
        self.set_up()

    @property
    def headers(self):
        return copy.copy(self._headers)

    def set_up(self):
        if self._files:
            self._body, headers = self.encode_multipart_form()
        else:
            self._body, headers = self.encode_form()
        self._headers.update(headers)

    def encode_form(self):
        body = urllib.urlencode(self._params) if self._params else None
        headers = {
            "Content-Type":"application/x-www-form-urlencoded",
            "Accept":"text/plain"
        }
        return body, headers

    def encode_multipart_form(self):
        body = encode_multipart_form(tuple(self._params.items()), self._files)
        headers = {
            'Content-Type': encode_multipart_content_type(),
            'Content-Length': str(len(body))
        }
        return body, headers


