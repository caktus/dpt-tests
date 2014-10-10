#!/usr/bin/env python
import logging
import datetime
import shutil
import time
import os
import requests

from contextlib import contextmanager
from github import Github
from subprocess import call, check_call, Popen, PIPE
from fabulaws.ubuntu.instances.base import UbuntuInstance

for l in ['fabulaws', 'fabric']:
    logger = logging.getLogger(l)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())

github_user = os.environ['GITHUB_USER']
github_password = os.environ['GITHUB_PASSWORD']


def check_output_(cmd):
    output = ''
    proc = Popen(cmd, stdout=PIPE)
    while proc.poll() is None:
        line = proc.stdout.readline()
        if line:
            print line.strip()
            output += line
    return output


@contextmanager
def github_cmd_line_auth(user, passwd, home):
    restore_netrc = False
    netrc = os.path.join(home, '.netrc')
    netrcbak = os.path.join(home, '.netrc.bak')
    if os.path.exists(netrc):
        restore_netrc = True
        os.rename(netrc, netrcbak)
    with open(netrc, 'w') as f:
        f.write('machine github.com\nlogin {0}\npassword {1}\n'.format(user, passwd))
    yield
    os.remove(netrc)
    if restore_netrc:
        os.path.rename(netrc, netrcbak)


class TestServer(UbuntuInstance):
    instance_type = 't1.micro'
    ami = 'ami-fa7dba92'  # us-east-1, 64-bit, ebs
    security_groups = ['dpt-test-sg']

    def __init__(self, environment, project_name):
        tags = {
            'environment': environment,
            'project': 'django-project-template',
            'project_name': project_name,
            'Name': project_name,
        }
        super(TestServer, self).__init__(
            tags=tags,
            terminate=True,
        )
        self.setup()


def bootstrap():
    name = datetime.datetime.now().strftime('dpt_test_%Y_%m_%d_%H_%M_%S')
    venv_name = 'env_{}'.format(name)
    proj_path = os.path.abspath(name)
    venv_path = os.path.abspath(venv_name)
    server = TestServer('staging', name)
    serv_name = server.instance.public_dns_name
    venv = lambda cmd, args: check_output_(['{0}/bin/{1}'.format(venv_path, cmd)] + args)
    fab = lambda args: venv('fab', ['-u', server.user, '-i', server.key_file.name,
                                    '--disable-known-hosts'] + args)
    try:
        g = Github(github_user, github_password)
        u = g.get_user()
        gh_repo = u.create_repo(name)
        check_call(['django-admin.py', 'startproject',
                    '--template=https://github.com/caktus/django-project-template'
                    '/zipball/dpt-test-support',
                    '--extension=py,rst', name])
        check_call(['virtualenv', 'env_{}'.format(name)])
        os.chdir(proj_path)
        check_call(['sed', '-i', 's/CHANGEME/{}/'.format(serv_name), 'fabfile.py'])
        check_call(['sed', '-i', 's/project_name: example/'
                    'project_name: {}/'.format(name),
                    os.path.join('conf', 'pillar', 'project.sls')])
        check_call(['sed', '-i', 's/staging.example.com/'
                    '{}/'.format(serv_name),
                    os.path.join('conf', 'pillar', 'staging', 'env.sls')])
        check_call(['sed', '-i', 's/git@github.com:CHANGEME\/CHANGEME.git/'
                    '{}/'.format(gh_repo.clone_url.replace('/', r'\/')),
                    os.path.join('conf', 'pillar', 'staging', 'env.sls')])
        shutil.copyfile(os.path.join('conf', 'pillar', 'secrets.ex'),
                        os.path.join('conf', 'pillar', 'staging', 'secrets.sls'))
        shutil.copyfile(os.path.join('conf', 'pillar', 'secrets.ex'),
                        os.path.join('conf', 'pillar', 'production', 'secrets.sls'))
        check_call(['git', 'init'])
        check_call(['git', 'config', 'user.email', 'dpt-test@example.com'])
        check_call(['git', 'config', 'user.name', 'DPT Tester'])
        check_call(['git', 'add', '*', '.*'])
        check_call(['git', 'commit', '-m', 'initial commit'])
        check_call(['git', 'remote', 'add', 'origin',
                    gh_repo.clone_url])
        env = os.environ.copy()
        env['HOME'] = os.path.abspath(os.path.dirname(proj_path))
        with github_cmd_line_auth(github_user, github_password, env['HOME']):
            check_call(['git', 'push', '-u', 'origin', 'master'], env=env)
        dev_reqs = os.path.join('requirements', 'dev.txt')
        venv('pip', ['install', '-q', '-r', dev_reqs])
        fab(['setup_master', '-H', serv_name])
        fab(['sync:1'])  # force overwrite of server secrets
        fab(['--set', 'environment=master', 'setup_minion:salt-master', '-H', serv_name])
        fab(['staging', 'setup_minion:web,balancer,db-master,cache,queue,worker', '-H', serv_name])
        sleep_time = 10
        # for some reason you need to run deploy a few times before it completes without error
        deploy_success = False
        for i in range(1800/sleep_time):
            if not deploy_success:
                output = fab(['staging', 'deploy'])
                deploy_success = 'Failed to authenticate' not in output
            time.sleep(sleep_time)
            try:
                r = requests.get('https://{}/admin/'.format(serv_name), verify=False)
            except requests.exceptions.ConnectionError, e:
                print 'caught exception, attempt={}, exception={}'.format(i, e)
                continue
            if r.status_code == 200:
                print 'got 200 status code (attempt={})!'.format(i)
                break
            print 'got bad status code ({}). attempt={}, content={}'.format(r.status_code,
                                                                            i, r.content)
    finally:
        try:
            gh_repo.delete()
        except NameError:
            pass
        call(['rm', '-rf', proj_path, venv_path])


if __name__ == "__main__":
    bootstrap()
