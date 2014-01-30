#!/bin/bash
#
# Script to control Yabi in dev and test
#

TOPDIR=$(cd `dirname $0`; pwd)

# break on error
set -e 

ACTION="$1"
PROJECT="$2"

PORT='8000'

PROJECT_NAME='yabi'
AWS_BUILD_INSTANCE='aws_rpmbuild_centos6'
AWS_TEST_INSTANCE='aws_yabi_test'
AWS_STAGING_INSTANCE='aws_syd_yabi_staging'
TARGET_DIR="/usr/local/src/${PROJECT_NAME}"
CLOSURE="/usr/local/closure/compiler.jar"
PIP_OPTS='--download-cache ~/.pip/cache --process-dependency-links'


if [ "${YABI_CONFIG}" = "" ]; then
    YABI_CONFIG="dev_mysql"
fi

VIRTUALENV="${TOPDIR}/virt_${PROJECT_NAME}"


usage() {
    echo ""
    echo "Usage ./develop.sh (status|test_mysql|test_postgresql|test_yabiadmin|lint|jslint|dropdb|start|stop|install|clean|purge|pipfreeze|pythonversion|syncmigrate|ci_remote_build|ci_remote_test|ci_rpm_publish|ci_remote_destroy|ci_staging|ci_staging_tests|ci_authorized_keys) (yabiadmin|celery|yabish)"
    echo ""
}


project_needed() {
    if ! test ${PROJECT}; then
        usage
        exit 1
    fi
}

settings() {
    case ${YABI_CONFIG} in
    test_mysql)
        export DJANGO_SETTINGS_MODULE="yabiadmin.testmysqlsettings"
        ;;
    test_postgresql)
        export DJANGO_SETTINGS_MODULE="yabiadmin.testpostgresqlsettings"
        ;;
    dev_mysql)
        export DJANGO_SETTINGS_MODULE="yabiadmin.settings"
        ;;
    dev_postgresql)
        export DJANGO_SETTINGS_MODULE="yabiadmin.postgresqlsettings"
        ;;
    *)
        echo "No YABI_CONFIG set, exiting"
        exit 1
    esac

    echo "Config: ${YABI_CONFIG}"
}


# ssh setup, make sure our ccg commands can run in an automated environment
ci_ssh_agent() {
    ssh-agent > /tmp/agent.env.sh
    source /tmp/agent.env.sh
    ssh-add ~/.ssh/ccg-syd-staging.pem
}


# build RPMs on a remote host from ci environment
ci_remote_build() {
    time ccg ${AWS_BUILD_INSTANCE} boot
    time ccg ${AWS_BUILD_INSTANCE} puppet
    time ccg ${AWS_BUILD_INSTANCE} shutdown:50

    EXCLUDES="('bootstrap'\, '.hg'\, 'virt*'\, '*.log'\, '*.rpm'\, 'screenshots'\, 'docs')"
    SSH_OPTS="-o StrictHostKeyChecking\=no"
    RSYNC_OPTS="-l"
    time ccg ${AWS_BUILD_INSTANCE} rsync_project:local_dir=./,remote_dir=${TARGET_DIR}/,ssh_opts="${SSH_OPTS}",extra_opts="${RSYNC_OPTS}",exclude="${EXCLUDES}",delete=True
    time ccg ${AWS_BUILD_INSTANCE} build_rpm:centos/yabi.spec,src=${TARGET_DIR}

    mkdir -p build
    ccg ${AWS_BUILD_INSTANCE} getfile:rpmbuild/RPMS/x86_64/yabi*.rpm,build/
}


# run tests on a remote host from ci environment
ci_remote_test() {
    TEST_PLAN=$1
    if [ "${TEST_PLAN}" = "" ]; then
        TEST_PLAN="test_mysql"
    fi

    echo "Test plan ${TEST_PLAN}"

    time ccg ${AWS_TEST_INSTANCE} boot
    time ccg ${AWS_TEST_INSTANCE} puppet
    time ccg ${AWS_TEST_INSTANCE} shutdown:100

    EXCLUDES="('bootstrap'\, '.hg'\, 'virt*'\, '*.log'\, '*.rpm'\, 'screenshots'\, 'docs'\, '*.pyc')"
    SSH_OPTS="-o StrictHostKeyChecking\=no"
    RSYNC_OPTS="-l"
    time ccg ${AWS_TEST_INSTANCE} rsync_project:local_dir=./,remote_dir=${TARGET_DIR}/,ssh_opts="${SSH_OPTS}",extra_opts="${RSYNC_OPTS}",exclude="${EXCLUDES}",delete=True
    time ccg ${AWS_TEST_INSTANCE} drun:"cd ${TARGET_DIR} && ./develop.sh purge"
    time ccg ${AWS_TEST_INSTANCE} drun:"cd ${TARGET_DIR} && ./develop.sh install"
    time ccg ${AWS_TEST_INSTANCE} drun:"cd ${TARGET_DIR} && ./develop.sh ${TEST_PLAN}"
    time ccg ${AWS_TEST_INSTANCE} shutdown:10
}


# publish rpms to testing repo
ci_rpm_publish() {
    time ccg publish_testing_rpm:build/yabi*.rpm,release=6
}


# destroy our ci build server
ci_remote_destroy() {
    ccg ${AWS_BUILD_INSTANCE} destroy
}


# puppet up staging which will install the latest rpm
ci_staging() {
    ccg ${AWS_STAGING_INSTANCE} boot
    ccg ${AWS_STAGING_INSTANCE} puppet
    ccg ${AWS_STAGING_INSTANCE} shutdown:50
}


# run tests on staging
ci_staging_tests() {
    # /tmp is used for test results because the apache user has
    # permission to write there.
    REMOTE_TEST_DIR=/tmp
    REMOTE_TEST_RESULTS=${REMOTE_TEST_DIR}/tests.xml

    # Grant permission to create a test database. Assume that database
    # user is same as project name for now.
    DATABASE_USER=${PROJECT_NAME}
    ccg ${AWS_STAGING_INSTANCE} dsudo:"su postgres -c \"psql -c 'ALTER ROLE ${DATABASE_USER} CREATEDB;'\""

    # fixme: this config should be put in nose.cfg or settings.py or similar
    EXCLUDES="--exclude\=yaphc --exclude\=esky --exclude\=httplib2"

    # Start virtual X server here to work around a problem starting it
    # from xvfbwrapper.
    ccg ${AWS_STAGING_INSTANCE} drunbg:"Xvfb \:0"

    sleep 2

    # firefox won't run without a profile directory, dbus and gconf
    # also need to write in home directory.
    ccg ${AWS_STAGING_INSTANCE} dsudo:"chown apache:apache /var/www"

    # Run tests, collect results
    ccg ${AWS_STAGING_INSTANCE} dsudo:"cd ${REMOTE_TEST_DIR} && env DISPLAY\=\:0 dbus-launch timeout -sHUP 30m ${PROJECT_NAME} test --verbosity\=2 --liveserver\=localhost\:8082\,8090-8100\,9000-9200\,7041 --noinput --with-xunit --xunit-file\=${REMOTE_TEST_RESULTS} ${TEST_LIST} ${EXCLUDES} || true"
    ccg ${AWS_STAGING_INSTANCE} getfile:${REMOTE_TEST_RESULTS},./
}


# we need authorized keys setup for ssh tests
ci_authorized_keys() {
    cat tests/test_data/yabitests.pub >> ~/.ssh/authorized_keys
}


# lint using flake8
lint() {
    project_needed
    ${VIRTUALENV}/bin/flake8 ${PROJECT} --ignore=E501 --count
}


# lint js, assumes closure compiler
jslint() {
    JSFILES="yabiadmin/yabiadmin/yabifeapp/static/javascript/*.js yabiadmin/yabiadmin/yabifeapp/static/javascript/account/*.js"
    for JS in $JSFILES
    do
        java -jar ${CLOSURE} --js $JS --js_output_file output.js --warning_level DEFAULT --summary_detail_level 3
    done
}


nosetests() {
    source ${VIRTUALENV}/bin/activate

    # Runs the end-to-end tests in the Yabitests project
    ${VIRTUALENV}/bin/nosetests --with-xunit --xunit-file=tests.xml -I sshtorque_tests.py -I torque_tests.py -I sshpbspro_tests.py -v tests yabiadmin/yabiadmin 
    #${VIRTUALENV}/bin/nosetests -v -w tests tests.simple_tool_tests
    #${VIRTUALENV}/bin/nosetests -v -w tests tests.s3_connection_tests
    #${VIRTUALENV}/bin/nosetests -v -w tests tests.ssh_tests
    #${VIRTUALENV}/bin/nosetests -v -w tests tests.sshpbspro_tests
    #${VIRTUALENV}/bin/nosetests -v -w tests tests.sshtorque_tests
    #${VIRTUALENV}/bin/nosetests -v -w tests tests.backend_execution_restriction_tests
    #${VIRTUALENV}/bin/nosetests -v -w tests tests.localfs_connection_tests
    #${VIRTUALENV}/bin/nosetests -v -w tests tests.rewalk_tests
    #${VIRTUALENV}/bin/nosetests -v -w tests tests.file_transfer_tests
    #${VIRTUALENV}/bin/nosetests -v -w tests tests.ssh_tests
    #${VIRTUALENV}/bin/nosetests -v -w tests tests.idempotency_tests
}


dropdb() {

    case ${YABI_CONFIG} in
    test_mysql)
        mysql -v -uroot -e "drop database test_yabi;" || true
        mysql -v -uroot -e "create database test_yabi default charset=UTF8;" || true
        ;;
    test_postgresql)
        psql -aeE -U postgres -c "SELECT pg_terminate_backend(pg_stat_activity.procpid) FROM pg_stat_activity where pg_stat_activity.datname = 'test_yabi'" && psql -aeE -U postgres -c "alter user yabiapp createdb;" template1 && psql -aeE -U postgres -c "alter database test_yabi owner to yabiapp" template1 && psql -aeE -U yabiapp -c "drop database test_yabi" template1 && psql -aeE -U yabiapp -c "create database test_yabi;" template1
        ;;
    dev_mysql)
	echo "Drop the dev database manually:"
        echo "mysql -uroot -e \"drop database dev_yabi; create database dev_yabi default charset=UTF8;\""
        exit 1
        ;;
    dev_postgresql)
	echo "Drop the dev database manually:"
        echo "psql -aeE -U postgres -c \"SELECT pg_terminate_backend(pg_stat_activity.procpid) FROM pg_stat_activity where pg_stat_activity.datname = 'dev_yabi'\" && psql -aeE -U postgres -c \"alter user yabiapp createdb;\" template1 && psql -aeE -U yabiapp -c \"drop database dev_yabi\" template1 && psql -aeE -U yabiapp -c \"create database dev_yabi;\" template1"
        exit 1
        ;;
    *)
        echo "No YABI_CONFIG set, exiting"
        exit 1
    esac
}


stopprocess() {
    set +e
    if ! test -e $1; then
        echo "PID file '$1' doesn't exist"
        return
    fi
    local pid=`cat $1`
    local pgrpid=""
    if test "kill_process_group" == "$2"; then
        pgrpid=$(ps -o pgrp= --pid $pid | tr -d ' ')
    fi
    
    if test -z $pgrpid; then
        kill $pid
    else
        kill -- -$pgrpid
    fi
    
    for I in {1..30} 
    do
        if ps --pid $pid > /dev/null; then
            sleep 1
        else
            break
        fi
    done

    if ps --pid $pid > /dev/null; then
        if test -z $pgrpid; then
            kill -9 $pid
        else
            kill -9 -- -$pgrpid
        fi
        echo "Forced stop"
    fi

    if test -e $1; then
        rm -f $1
    fi
    set -e
}


stopyabiadmin() {
    echo "Stopping Yabi admin"
    stopprocess yabiadmin-develop.pid "kill_process_group"
}


stopceleryd() {
    echo "Stopping celeryd"
    stopprocess celeryd-develop.pid
}


stopyabi() {
    case ${PROJECT} in
    'yabiadmin')
        stopyabiadmin
        stopceleryd
        ;;
    'celery')
        stopceleryd
        ;;
    '')
        stopyabiadmin
        stopceleryd
        ;;
    *)
        echo "Cannot stop ${PROJECT}"
        usage
        exit 1
        ;;
    esac
}


installyabi() {
    # check requirements
    which virtualenv >/dev/null

    echo "Install yabiadmin"
    virtualenv ${VIRTUALENV}
    ${VIRTUALENV}/bin/pip install 'pip>=1.5,<1.6' --upgrade
    ${VIRTUALENV}/bin/pip --version
    pushd yabiadmin
    ${VIRTUALENV}/bin/pip install ${PIP_OPTS} -e .[dev,mysql,postgresql,tests]
    popd

    echo "Install yabish"
    pushd yabish
    ${VIRTUALENV}/bin/pip install ${PIP_OPTS} -e .
    popd
}


startyabiadmin() {
    if test -e yabiadmin-develop.pid; then
        echo "pid file exists for yabiadmin"
        return
    fi

    echo "Launch yabiadmin (frontend) http://localhost:${PORT}"
    mkdir -p ~/yabi_data_dir
    . ${VIRTUALENV}/bin/activate
    syncmigrate

    case ${YABI_CONFIG} in
    test_*)
        ${VIRTUALENV}/bin/gunicorn_django -b 0.0.0.0:${PORT} --pid=yabiadmin-develop.pid --log-file=yabiadmin-develop.log --daemon ${DJANGO_SETTINGS_MODULE} -t 300 -w 5
        ;;
    *)
        ${VIRTUALENV}/bin/django-admin.py runserver_plus 0.0.0.0:${PORT} --settings=${DJANGO_SETTINGS_MODULE} > yabiadmin-develop.log 2>&1 &
        echo $! > yabiadmin-develop.pid
    esac
}


# django syncdb, migrate and collect static
syncmigrate() {
    echo "syncdb"
    ${VIRTUALENV}/bin/django-admin.py syncdb --noinput --settings=${DJANGO_SETTINGS_MODULE} 1> syncdb-develop.log
    echo "migrate"
    ${VIRTUALENV}/bin/django-admin.py migrate --settings=${DJANGO_SETTINGS_MODULE} 1> migrate-develop.log
    echo "collectstatic"
    ${VIRTUALENV}/bin/django-admin.py collectstatic --noinput --settings=${DJANGO_SETTINGS_MODULE} 1> collectstatic-develop.log
}


startceleryd() {
    if test -e celeryd-develop.pid; then
        echo "pid file exists for celeryd"
        return
    fi

    echo "Launch celeryd (message queue)"
    CELERY_CONFIG_MODULE="settings"
    CELERYD_CHDIR=`pwd`
    CELERYD_OPTS="-E --loglevel=INFO --logfile=celeryd-develop.log --pidfile=celeryd-develop.pid"
    CELERY_LOADER="django"
    DJANGO_PROJECT_DIR="${CELERYD_CHDIR}"
    PROJECT_DIRECTORY="${CELERYD_CHDIR}"
    export CELERY_CONFIG_MODULE DJANGO_SETTINGS_MODULE DJANGO_PROJECT_DIR CELERY_LOADER CELERY_CHDIR PROJECT_DIRECTORY CELERYD_CHDIR
    setsid ${VIRTUALENV}/bin/celeryd ${CELERYD_OPTS} 1>/dev/null 2>/dev/null &
}


celeryevents() {
    echo "Launch something to monitor celeryd (message queue)"
    echo "It will not work with database transports :/"
    DJANGO_PROJECT_DIR="${CELERYD_CHDIR}"
    PROJECT_DIRECTORY="${CELERYD_CHDIR}"
    export CELERY_CONFIG_MODULE DJANGO_SETTINGS_MODULE DJANGO_PROJECT_DIR CELERY_LOADER CELERY_CHDIR PROJECT_DIRECTORY CELERYD_CHDIR
    echo ${DJANGO_SETTINGS_MODULE}

    # You need to be using rabbitMQ for this to work
    ${VIRTUALENV}/bin/django-admin.py celery flower --settings=${DJANGO_SETTINGS_MODULE}

    # other monitors I looked at
    #${VIRTUALENV}/bin/django-admin.py celeryd --help --settings=${DJANGO_SETTINGS_MODULE}
    #${VIRTUALENV}/bin/django-admin.py djcelerymon 9000 --settings=${DJANGO_SETTINGS_MODULE}
    #${VIRTUALENV}/bin/django-admin.py celerycam --settings=${DJANGO_SETTINGS_MODULE}
    #${VIRTUALENV}/bin/django-admin.py celery events --settings=${DJANGO_SETTINGS_MODULE}
}


startyabi() {
    case ${PROJECT} in
    'yabiadmin')
        startyabiadmin
        startceleryd
        ;;
    'celery')
        startceleryd
        ;;
    '')
        startyabiadmin
        startceleryd
        ;;
    *)
        echo "Cannot start ${PROJECT}"
        usage
        exit 1
        ;;
    esac
}


yabistatus() {
    set +e
    if test -e yabiadmin-develop.pid; then
        ps -f -p `cat yabiadmin-develop.pid`
    else 
        echo "No pid file for yabiadmin"
    fi
    if test -e celeryd-develop.pid; then
        ps -f -p `cat celeryd-develop.pid`
    else 
        echo "No pid file for celeryd"
    fi
    set -e
}


pythonversion() {
    ${VIRTUALENV}/bin/python -V
}


pipfreeze() {
    echo 'yabiadmin pip freeze'
    ${VIRTUALENV}/bin/pip freeze
}


yabiclean() {
    echo "rm -rf ~/yabi_data_dir/*"
    rm -rf ~/yabi_data_dir/*
    rm -rf yabiadmin/scratch/*
    rm -rf yabiadmin/scratch/.uploads
    find yabiadmin -name "*.pyc" -exec rm -rf {} \;
    find yabish -name "*.pyc" -exec rm -rf {} \;
    find tests -name "*.pyc" -exec rm -rf {} \;
}


yabipurge() {
    rm -rf ${VIRTUALENV}
    rm -f *.log
}


dbtest() {
    local noseretval
    stopyabi
    dropdb
    startyabi
    nosetests
    noseretval=$?
    stopyabi
    exit $noseretval
}


case ${PROJECT} in
'yabiadmin' | 'celery' |  'yabish' | '')
    ;;
*)
    usage
    exit 1
    ;;
esac

case $ACTION in
pythonversion)
    pythonversion
    ;;
pipfreeze)
    pipfreeze
    ;;
test_mysql)
    YABI_CONFIG="test_mysql"
    settings
    dbtest
    ;;
test_postgresql)
    YABI_CONFIG="test_postgresql"
    settings
    dbtest
    ;;
lint)
    lint
    ;;
jslint)
    jslint
    ;;
dropdb)
    settings
    dropdb
    ;;
syncmigrate)
    settings
    syncmigrate
    ;;
stop)
    settings
    stopyabi
    ;;
start)
    settings
    startyabi
    ;;
status)
    yabistatus
    ;;
install)
    settings
    stopyabi
    time installyabi
    ;;
celeryevents)
    settings
    celeryevents
    ;;
ci_remote_build)
    ci_ssh_agent
    ci_remote_build
    ;;
ci_remote_test)
    ci_ssh_agent
    ci_remote_test
    ;;
ci_remote_test_postgresql)
    ci_ssh_agent
    ci_remote_test test_postgresql
    ;;
ci_remote_test_mysql)
    ci_ssh_agent
    ci_remote_test test_mysql
    ;;
ci_remote_test_yabiadmin_mysql)
    ci_ssh_agent
    ci_remote_test test_yabiadmin_mysql
    ;;
ci_remote_destroy)
    ci_ssh_agent
    ci_remote_destroy
    ;;
ci_rpm_publish)
    ci_ssh_agent
    ci_rpm_publish
    ;;
ci_authorized_keys)
    ci_authorized_keys
    ;;
ci_staging)
    ci_ssh_agent
    ci_staging
    ;;
ci_staging_tests)
    ci_ssh_agent
    ci_staging_tests
    ;;
clean)
    settings
    stopyabi
    yabiclean 
    ;;
purge)
    settings
    stopyabi
    yabiclean
    yabipurge
    ;;
*)
    usage
    ;;
esac
