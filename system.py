"""Core system for magor_sgenglish."""

from __future__ import print_function

import argparse
import json
import itertools
import logging
import os
import shutil
import subprocess

try:
    from slugify import slugify
except ImportError:
    subprocess.call(['pip2', 'install', '--user', 'python-slugify'])
    from slugify import slugify

CUR_DIR = os.path.dirname(os.path.realpath(__file__))
MODULES_DIR = os.path.join(CUR_DIR, 'modules/')
DATA_DIR = os.path.join(CUR_DIR, 'data/')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
CRAWL_DIR = os.path.join(CUR_DIR, 'crawl/')
if not os.path.exists(CRAWL_DIR):
    os.makedirs(CRAWL_DIR)

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s (%(name)s | %(levelname)s) : %(message)s')
LOG = logging.getLogger('system')


class Manifest(object):
    """
    Class holding the system and modular manifests for a system instance.
    Syntax: Manifest(sys_mnft=os.path.join(CUR_DIR, 'manifest.json'))
    """

    def __init__(self, sys_mnft=os.path.join(CUR_DIR, 'manifest.json')):
        """Load the system and modular manifests."""
        LOG.info('Loading manifests...')
        # system manifest
        with open(sys_mnft, 'r') as mnft:
            manifest = json.load(mnft)
        self.processes = manifest['processes']
        self.procedures = manifest['procedures']
        self.valid_types = [x.decode('utf-8') for x in manifest['file_types']
                            ['audio'] + manifest['file_types']['video']]
        # modular manifests
        manifest['modules'] = dict()
        for mod_id in os.listdir(MODULES_DIR):
            mod_mnft = os.path.join(MODULES_DIR, mod_id, 'manifest.json')
            if os.path.exists(mod_mnft):  # check for modular manifest
                with open(mod_mnft, 'r') as mnft:
                    manifest['modules'][mod_id] = json.load(mnft)
        self.modules = manifest['modules']
        # cache it somewhere
        with open(os.path.join(CUR_DIR, 'manifest_cache.json'), 'w') as mnft:
            json.dump(manifest, mnft, sort_keys=True, indent=4)

    def check_modules(self):
        """Check modular manifests for consistency, disable violating modules."""
        mod_violate = list()
        # find violating modules
        for mod_id, mod_ in self.modules.items():
            mod_path = os.path.join(MODULES_DIR, mod_id)
            mod_reqs = mod_['requires'] + ['module.py']
            for mod_req in mod_reqs:
                mod_req_path = os.path.join(mod_path, mod_req)
                if not os.path.exists(mod_req_path):
                    LOG.info('Cannot find module %s requirement at %s',
                             mod_id, mod_req_path)
                    mod_violate.append(mod_id)
                    break
        # disable violating modules
        for mod_id in mod_violate:
            del self.modules[mod_id]
        LOG.info('Valid modules: %s', ', '.join(self.modules.keys()))

    def check_processes(self):
        """Check processes for consistency, disable violating process components."""
        modules_set = set(self.modules)
        for process_id in self.processes:
            # find violating procedures
            LOG.info('Checking process %s', process_id)
            proc_violate = list()
            proc_ = self.processes[process_id]
            for procedure_id in proc_:
                # process' procedure not in manifest
                if procedure_id not in self.procedures.keys():
                    LOG.info('Procedure %s does not exist', procedure_id)
                    proc_violate.append(procedure_id)
                    break
                # process' procedure's modules are different from procedure definition
                elif set(proc_[procedure_id].keys()) != set(self.procedures[procedure_id]):
                    LOG.info(
                        'Not all modules in procedure %s are defined', procedure_id)
                    proc_violate.append(procedure_id)
                    break
                else:
                    modules = ['{}-{}'.format(mod, ver)
                               for mod, ver in proc_[procedure_id].items()]
                    # some procedure's modules not in manifest
                    if not set(modules).issubset(modules_set):
                        LOG.info('Modules %s does not exist', ', '.join(
                            set(modules).difference(modules_set)))
                        proc_violate.append(procedure_id)
            # disable violating procedures
            for procedure_id in proc_violate:
                del self.processes[process_id][procedure_id]
            LOG.info('Valid procedures: %s', ', '.join(
                self.processes[process_id].keys()))

    def check_all(self):
        """Wrapper for all manifest checks."""
        LOG.info('Startup manifest checks...')
        self.check_modules()
        self.check_processes()


class Operation(object):
    """
    Processing tasks.
    Syntax: Operation(manifest, process_id, procedure_id,
                      file_name=None, file_id=None, simulate=False)
    """

    def __init__(self, manifest, process_id, procedure_id,
                 file_name=None, file_id=None, simulate=False):
        if not (file_name or file_id):
            self.valid = False  # invalid operation
        elif file_name:
            self.file_name = file_name
            self.file_id = slugify(os.path.splitext(file_name)[0])
            self.valid = True
        elif file_id:
            self.file_name = None
            self.file_id = file_id
            self.valid = True
        self.manifest = manifest
        self.process_id = process_id
        self.procedure_id = procedure_id
        self.simulate = simulate
        self.working_dir = os.path.join(
            DATA_DIR, self.process_id, self.file_id)

        # set later during verify()
        self.module_list = None

    def __repr__(self):
        result = 'Operation(process_id={}, procedure_id={}, file_name={}, file_id={})'.format(
            self.process_id, self.procedure_id, self.file_name, self.file_id)
        return result

    def verify(self):
        """Verify the operation."""
        # check for valid operation
        if not self.valid:
            return False

        # check for valid file_name and file_id
        if self.file_name:
            if (os.path.splitext(self.file_name)[1].lower()) not in self.manifest.valid_types:
                LOG.info('%s is of invalid type', self.file_name)
                return False
        elif self.file_id:
            if not os.path.exists(self.working_dir):
                LOG.info('%s does not exist', self.file_id)
                return False

        # check for valid process & procedure
        if self.process_id not in self.manifest.processes.keys():
            LOG.info('Process %s does not exist', self.process_id)
            return False
        elif self.procedure_id not in self.manifest.processes[self.process_id].keys():
            LOG.info('Procedure %s does not exist', self.procedure_id)
            return False

        # if all is well, set module list
        self.module_list = [
            '{}-{}'.format(mod,
                           self.manifest.processes[self.process_id][self.procedure_id][mod])
            for mod in self.manifest.procedures[self.procedure_id]]
        return True

    def import_file(self):
        """Import the file into /data."""
        # init paths
        raw_dir = os.path.join(self.working_dir, 'raw/')
        if not os.path.exists(raw_dir):
            os.makedirs(raw_dir)

        if self.file_name:
            file_path = os.path.join(CRAWL_DIR, self.file_name)
            raw_file = os.path.join(raw_dir, self.file_name)
            if os.path.exists(raw_file):
                LOG.info('Previously imported to %s', raw_file)
            else:
                shutil.copy2(file_path, raw_dir)
                LOG.info('Imported %s to %s', file_path, raw_dir)
        else:
            if os.path.exists(raw_dir) and os.listdir(raw_dir):
                LOG.info('Previously imported to %s', raw_dir)

    def call(self, module_id):
        """Atom instruction to call a module."""
        try:
            exec_ = os.path.join(MODULES_DIR, module_id, 'module.py')
            args = ['python', exec_, self.process_id, self.file_id]
            subprocess.call(args)
            return True
        except BaseException:
            LOG.info('Error occured.', exc_info=True)
            return False

    def pipeline(self):
        """Pipeline for processing."""
        print('\n')
        LOG.info('Process: %s', self.process_id)
        LOG.info('Procedure: %s', self.procedure_id)
        if self.file_name:
            LOG.info('Filename: %s', self.file_name)
        LOG.info('File ID: %s', self.file_id)
        if self.simulate:
            LOG.info('%s', self.__repr__())
            return
        if self.verify():
            self.import_file()
            for mod_id in self.module_list:
                if not self.call(mod_id):
                    # module failure, terminate operation
                    LOG.info('Pipeline failed for %s at procedure %s, module %s',
                             self.file_id, self.procedure_id, mod_id)
                    return
            LOG.info('Pipeline completed for %s using procedure %s',
                     self.file_id, self.procedure_id)
        else:
            LOG.info('Verification failed for %s using procedure %s',
                     self.file_id, self.procedure_id)


def setup(args):
    """Setup all modules."""
    LOG.info('Starting setup...')
    if args.all:  # setup all modules
        for mod_id in os.listdir(MODULES_DIR):
            try:
                args = [os.path.join(MODULES_DIR, mod_id, 'setup')]
                subprocess.call(args)
                LOG.info('Setup successful for module %s', mod_id)
            except BaseException:
                LOG.info('Setup failed for module %s', mod_id)
    elif args.modules:  # setup specified modules
        for mod_id in args.modules:
            try:
                args = [os.path.join(MODULES_DIR, mod_id, 'setup')]
                subprocess.call(args)
                LOG.info('Setup successful for module %s', mod_id)
            except BaseException:
                LOG.info('Setup failed for module %s', mod_id)


def workflow(manifest, process_id, procedures, file_names, file_ids,
             test=False, simulate=False):
    """Processing workflow."""
    if test:  # manifest check only, no processing
        return

    # init path
    if process_id not in manifest.processes.keys():
        LOG.info('Process %s does not exist', process_id)
        return
    else:
        process_dir = os.path.join(DATA_DIR, process_id)
        if not os.path.exists(process_dir):
            os.makedirs(process_dir)

    valid_procs = [
        i for i in procedures if i in manifest.processes[process_id].keys()]
    if not (file_names or file_ids):  # do everything
        workflow(manifest, process_id, valid_procs, file_names=os.listdir(
            CRAWL_DIR), file_ids=os.listdir(process_dir), simulate=simulate)

    # populate valid_names and valid_ids, check for duplicates
    valid_names = list()
    valid_ids = list()
    if file_names:
        valid_names = [i for i in file_names if os.path.isfile(
            os.path.join(CRAWL_DIR, i))]
    if file_ids:
        tmp_valid_ids = [i for i in file_ids if os.path.isdir(
            os.path.join(process_dir, i))]
        # check duplicates (file_ids where raw file is already inside valid_names)
        valid_ids = [i for i in tmp_valid_ids if os.listdir(
            os.path.join(process_dir, i, 'raw/'))[0] not in valid_names]

    # process
    if valid_names:
        for i in itertools.product(valid_names, valid_procs):
            Operation(manifest, process_id,
                      i[1], file_name=i[0], simulate=simulate).pipeline()
    if valid_ids:
        for i in itertools.product(valid_ids, valid_procs):
            Operation(manifest, process_id,
                      i[1], file_id=i[0], simulate=simulate).pipeline()


def process(args):
    """Wrapper for workflow."""
    manifest = Manifest()
    manifest.check_all()
    workflow(manifest, args.process_id, args.procedures,
             args.files, args.ids, args.test, args.simulate)


def main():
    """Entry point for the system."""
    # top-level argument parser
    arg_parser = argparse.ArgumentParser()
    sub_parsers = arg_parser.add_subparsers()

    # setup sub-command
    setup_parser = sub_parsers.add_parser('setup', help='setup the system')
    setup_parser.add_argument(
        '-m', '--modules', metavar='module_id', help='module_ids to setup', nargs='*')
    setup_parser.add_argument(
        '-a', '--all', action='store_true', help='setup all available modules')
    setup_parser.set_defaults(func=setup)

    # process sub-command
    process_parser = sub_parsers.add_parser('process', help='process files')
    process_parser.add_argument(
        'process_id', help='process_id for this run', nargs='?')
    process_parser.add_argument('-p', '--procedures', metavar='procedure_id',
                                help='procedures to run', nargs='*')
    process_parser.add_argument(
        '-f', '--files', metavar='file_name', help='file_names to process', nargs='*')
    process_parser.add_argument(
        '-i', '--ids', metavar='file_id', help='file_ids to process', nargs='*')

    process_parser.add_argument(
        '-t', '--test', action='store_true', help='just do system checks and exit')
    process_parser.add_argument('-n', '--simulate', action='store_true',
                                help='simulate the run, without processing any file')
    process_parser.set_defaults(func=process)

    # parse args and perform operations
    args = arg_parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
