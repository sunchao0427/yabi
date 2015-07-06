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
from yabi.backend.backend import exec_credential
from yabi.backend.basebackend import BaseBackend
import logging
from yabi.backend.utils import submission_script
logger = logging.getLogger(__name__)


class ExecBackend(BaseBackend):

    @classmethod
    def factory(cls, task):
        assert(task)
        assert(task.execscheme)

        backend = cls.create_backend_for_scheme(task.execscheme)

        if not backend:
            raise Exception('No valid scheme is defined for task {0}'.format(task.id))

        backend.yabiusername = task.job.workflow.user.name
        backend.task = task
        backend.cred = exec_credential(backend.yabiusername, task.job.exec_backend)
        backend.backend = backend.cred.backend if backend.cred is not None else None
        return backend

    def get_submission_script(self, host, working):
        """Get the submission script for this backend."""
        if self.task.job.tool.submission.strip() != '':
            template = self.task.job.tool.submission
        elif self.cred.submission.strip() != '':
            template = self.cred.submission
        else:
            template = self.cred.backend.submission

        return submission_script(
            template=template,
            working=working,
            command=self.task.command,
            modules=self.task.job.module,
            cpus=self.task.job.cpus,
            memory=self.task.job.max_memory,
            walltime=self.task.job.walltime,
            yabiusername=self.yabiusername,
            username=self.cred.credential.username,
            host=host,
            queue=self.task.job.queue,
            tasknum=self.task.task_num,
            tasktotal=self.task.job.task_total,
            envvars=self.task.envvars)

    def submit_task(self):
        raise NotImplementedError("")

    def poll_task_status(self):
        raise NotImplementedError("")

    def abort_task(self):
        raise NotImplementedError("")