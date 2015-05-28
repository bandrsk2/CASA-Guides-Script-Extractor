#standard library imports
import numpy as np
import os
import platform
import socket
import subprocess
import sys

#library specific imports
import benchmark
import parameters

#-the sharing and passing around of variables is really a mess between the
# benchmark and machine classes right now

def makeReport(files):
    """Caluclate the mean and standard deviation of times from .summary files.

    Parameters
    ----------
    files : list (of str)
       List of strings specifying the absolute paths to .summary files from
       benchmarking to gather total times from.

    Returns
    -------
    Tuple containing (average, standard deviation, list of all total times)

    Notes
    -----
    Loop over the list in files, search each for a line starting with
    'Total time: ' and grab the total time from that line. From those times
    compute the average and standard deviation.
    """
    times = np.empty(len(files))
    for i,f in enumerate(files):
        fileObj = open(f)
        for line in fileObj.readlines():
            if line[0:12] == 'Total time: ':
                time = line.split(' ')
                time = time[2]
                time = float(time)
                times[i] = time
                break
        fileObj.close()
    avg = times.mean()
    std = times.std()
    return (avg, std, times)


class machine:
    """A class associated with all benchmarking done on a single computer.

    Methods
    -------
    __init__
    runBenchmarks
    writeToWrappingLog
    _printAndFlush

    Instance Variables
    ------------------
    _CASAglobals : dict
       Dictionary returned by Python globals() function within the CASA
       namespace (environment). Avoid altering this since it is the namespace
       that allows us to execfile a script with all of the CASA infrastructure.

    dataSets : list
       List of strings containing names of data sets to be benchmarked. Names
       must match the dictionary variable names in parameters.py.

    jobs: dict
       Container for each benchmark instance to be run on this machine along
       with information on whether to download the raw data, the number of
       benchmarking iterations desired and which step(s) (cal, im or both) to
       run.

    workDir : str
       Absolute path to directory where all benchmarking will run. A separate
       directory for each data set will be created here and each benchmark
       iteration will be contained in a dedicated directory below that.

    hostName : str
       Name of the computer this class is associated with.

    os : str
       Description of underlying platform associated to hostName.

    lustreAccess : bool
       Determines whether this computer has access to the /lustre/naasc/
       filesystem (it is hard-coded to simply check for the existence of that
       directory).

    pythonVersion : str
       major.minor.patchlevel version number for currently running Python.

    casaVersion : str
       Version number for currently running CASA.

    casaRevision : str
       Revision number for currently running CASA.

    machineLog : list
       List of strings of absolute paths to text files containing machine
       information. Will be called [hostname]_machine_info.log and will be
       stored in the data set directories.

    totalMemBytes : float
       Total number of physical bytes of memory (RAM) available on the machine.

    nCores : int
       Total number of physical cores available on the machine.

    cpuFreqMHz : float
       Processor frequency in MHz.

    wrappingLog : list
       Absolute paths to text files where status reporting are written. This
       includes starting data set benchmarking and index of iteration executing.
       Will be called [hostname]_machine_wrapping.log and will be stored in the
       data set directories.

    quiet : bool
       Switch to determine if status messages are printed to the terminal or not.
       These messages are always written to [hostname]_machine_wrapping.log.
    """

    def __init__(self, CASAglobals=None, scriptDir='', dataSets=list(), \
                 nIters=list(), skipDownloads=list(), steps=list(), \
                 scriptsSources=list(), workDir='./', quiet=False):
        """Prepare all machine instance variables for all the other methods.

        Returns
        -------
        None

        Parameters
        ----------
        CASAglobals : dict
           Dictionary returned by Python globals() function within the CASA
           namespace (environment). Simply pass the return value of the globals()
           function from within CASA where this class should be instantiated
           within.

        scriptDir : str
           Absolute path to directory containing the benchmarking module files.

        dataSets : list
           List of strings containing names of data sets to be benchmarked. Names
           must match the dictionary variable names in parameters.py.

        nIters : list
           List of integers specifying how many times each data set should be run
           through benchmarking. These are matched to the data set in the same
           position in the dataSets list.

        skipDownloads : list
           List of booleans specifying if the raw data download step should be
           skipped or not. False means download the data from the URL provided in
           parameters.py variable. These are matched to the data set in the same
           position in the dataSets list.

        steps : list
           List of strings specifying which stage (calibration, imaging or both)
           each set of iterations should run. Accepted values are 'cal', 'im' or
           'both'.

        scriptsSources : list
           List of strings specifying where to extract calibration and/or imaging
           script(s) from. Accepted values are 'web' or 'disk' for extracting the
           CASA commands from a web-source or from a file saved on disk,
           respectively.

        workDir : str
           Absolute path to directory where all benchmarking will run. A separate
           directory for each data set will be created here and each benchmark
           iteration will be contained in a dedicated directory below that.
           Defaults to current directory.

        quiet : bool
           Switch to determine if status messages are printed to the terminal or
           not. These messages are always written to
           [hostname]_machine_wrapping.log.

        Notes
        -----
        Initialize all of the machine instance variables so that all of the
        other object methods will operate correctly. This does not mean all of
        the other methods will be successful (since many of them need additional
        information or other methods to be run first) but it means that each
        method will not crash as a result of something not being defined. Checks
        are run on all of the required inputs to make sure the object will be
        well formed upon return. Also, gather machine specific information
        (OS, CPU frequency, total physical memory, etc.).
        """
        #for telling where printed messages originate from
        fullFuncName = __name__ + '::__init__'
        indent = len(fullFuncName) + 2

        #check that we have CASA globals
        if not CASAglobals:
            raise ValueError('Value returned by globals() function in ' + \
                             'CASA environment must be given.')
        self._CASAglobals = CASAglobals

        #add script directory to Python path if need be
        if scriptDir == '':
            raise ValueError('Path to benchmarking scripts must be given.')
        scriptDir = os.path.abspath(scriptDir) + '/'
        self.scriptDir = scriptDir
        if scriptDir not in sys.path:
            sys.path.append(self.scriptDir)

        #gather details of computer and installed packages
        self.hostName = socket.gethostname()
        self.os = platform.platform()
        self.lustreAccess = os.path.isdir('/lustre/naasc/')
        self.pythonVersion = platform.python_version()
        self.casaVersion = self._CASAglobals['casadef'].casa_version
        self.casaRevision = self._CASAglobals['casadef'].subversion_revision

        #gather total memory, ncores and CPU frequency
        if 'Darwin' in self.os:
            out = subprocess.check_output('hostinfo', shell=True)
            out = out.split('\n')
            memBytes = [s for s in out if 'Primary memory available:' in s]
            memBytes = memBytes[0].split(':')
            memBytes = memBytes[1].strip()
            memBytes = memBytes.split(' ')
            unit = memBytes[1]
            if 'gigabytes' in unit:
                self.totalMemBytes = float(memBytes[0])*1e9
            elif 'megabytes' in unit:
                self.memBtyes = float(memBytes[0])*1e6
            else:
                raise ValueError('Memory quanta not recognized from ' + \
                                 'hostinfo output: \n"', out, '"')
            nCores = [s for s in out if 'processors are physically available.' \
                      in s]
            nCores = nCores[0].split(' ')[0]
            self.nCores = int(nCores)
            out = subprocess.check_output('sysctl machdep.cpu.brand_string', \
                                          shell=True)
            cpuFreq = out.split('@')
            cpuFreq = [s for s in cpuFreq if 'Hz' in s]
            if 'GHz' in cpuFreq[0]:
                cpuFreq = cpuFreq[0].split('GHz')
                self.cpuFreqMHz = float(cpuFreq[0].strip())*1e3
            elif 'MHz' in cpuFreq[0]:
                cpuFreq = cpuFreq[0].split('MHz')
                self.cpuFreqMHz = float(cpuFreq[0].strip())*1e3
            else:
                raise ValueError('CPU frequency quanta not recognized from ' + \
                                 'sysctl output: "' + out + '"')
        else:
            self.totalMemBytes = \
                os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')
            out = subprocess.check_output('lscpu', shell=True)
            out = out.split('\n')
            coresPsocket = [s for s in out if 'Core(s) per socket:' in s]
            coresPsocket = coresPsocket[0].split(':')
            coresPsocket = int(coresPsocket[1].strip())
            nSockets = [s for s in out if 'Socket(s):' in s]
            nSockets = nSockets[0].split(':')
            nSockets = int(nSockets[1].strip())
            self.nCores = coresPsocket*nSockets
            cpuFreq = [s for s in out if 'z:' in s]
            cpuFreq = cpuFreq[0].split(':')
            self.cpuFreqMHz = float(cpuFreq[1].strip())

        #store info about which data sets will be benchmarked
        if len(dataSets) == 0:
            raise ValueError('At least one data set must be specified for ' + \
                             'benchmarking.')
        for dataSet in dataSets:
            if not hasattr(parameters, dataSet):
                raise ValueError('Data set name "' + dataSet + \
                                 '" not recognized.')
            if dataSet[-2:] != self.casaVersion[0] + self.casaVersion[2]:
                raise ValueError('Data set name "' + dataSet + \
                                 '" does not match currently running ' + \
                                 'CASA version "' + self.casaVersion + '".')
        self.dataSets = dataSets
        if len(steps) == 0:
            steps = ['both']*len(self.dataSets)
        self.jobs = dict()
        for dataSet in self.dataSets:
            self.jobs[dataSet] = dict()
            self.jobs[dataSet]['benchmarks'] = list()
        if len(nIters) != len(self.dataSets):
            raise ValueError('nIters integer list must be of same length ' + \
                             'as dataSets list.')
        if len(skipDownloads) != len(self.dataSets):
            raise ValueError('skipDownloads boolean list must be of same ' + \
                             'length as dataSets list.')
        if len(steps) != len(self.dataSets):
            raise ValueError('steps string list must be of same length as ' + \
                             'dataSets list.')
        if len(scriptsSources) != len(self.dataSets):
            raise ValueError('scriptsSources string list must be of same ' + \
                             'length as dataSets list.')
        for i,dataSet in enumerate(self.dataSets):
            if type(nIters[i]) != int:
                raise TypeError('nIters must be a list of all integers.')
            if type(skipDownloads[i]) != bool:
                raise TypeError('skipDownloads must be a list of all booleans.')
            if steps[i] != 'cal' and steps[i] != 'im' and steps[i] != 'both':
                raise ValueError('Elements in steps must be either "cal", ' + \
                                 '"im" or "both".')
            if scriptsSources[i] != 'web' and scriptsSources[i] != 'disk':
                raise ValueError('Elements in scriptsSources must be either ' + \
                                 '"web" or "disk".')
            self.jobs[dataSet]['nIters'] = nIters[i]
            self.jobs[dataSet]['skipDownload'] = skipDownloads[i]
            self.jobs[dataSet]['step'] = steps[i]
            self.jobs[dataSet]['scriptsSource'] = scriptsSources[i]

        #initialize the working directory
        if not os.path.isdir(workDir):
            raise ValueError("Working directory '" + workDir + "' " + \
                             'does not exist.')
        if workDir == './': workDir = os.getcwd()
        if workDir[-1] != '/': workDir += '/'
        if workDir[0] != '/':
            raise ValueError('Working directory must be specified as an ' + \
                             'absolute path.')
        self.workDir = workDir

        #initialize some variables
        if type(quiet) != bool:
            raise TypeError('quiet must be a boolean.')
        self.quiet = quiet
        self.machineLog = self.workDir + self.hostName + '_machine_info.log'
        self.wrappingLog = self.workDir + self.hostName + \
                           '_machine_wrapping.log'

        #fill out machine info log
        f = open(self.machineLog, 'w')
        f.write('==Machine and Software Details==\n')
        f.write('Host name: ' + self.hostName + '\n')
        f.write('Operating system: ' + self.os + '\n')
        f.write('Total physical memory (bytes): ' + \
                str(self.totalMemBytes) + '\n')
        f.write('Total physical cores: ' + str(self.nCores) + '\n')
        f.write('CPU Frequency (MHz): ' + str(self.cpuFreqMHz) + '\n')
        f.write('lustre access: ' + str(self.lustreAccess) + '\n')
        f.write('CASA version: ' + self.casaVersion + ' (r' + \
                self.casaRevision + ')\n')
        f.close()


    def runBenchmarks(self, cleanUp=False):
        """Run all data sets the specified number of iterations with benchmark.

        Parameters
        ----------
        cleanUp : bool
           Determine whether benchmark::removeCurrentRedDir is run at the end of
           each benchmark to conserve disk space. Defaults to False (do not
           remove reduction directory).

        Returns
        -------
        None

        Notes
        -----
        Iterate over each data set setup for benchmarking for the associated
        number of iterations. For each iteration, instantiate a dedicated
        benchmark object and store it in the jobs attribute. benchmark
        class methods run are benchmark, downloadData (optional), extractData,
        doScriptExtraction, useOtherBmarkScripts (optional), runGuideScript,
        removeCurrentRedDir (optional) and removeTarDir (optional). Make the data
        set directories if they are not already present. Also try to only do the
        data extraction once:
          -do the extraction on the first iteration
          -if the previous benchmark was successful, run useOtherBmarkScripts on
           the previous benchmark instance for the next iteration
          -if the previous failed then do the extraction for the next like normal
        """
        #for telling where printed messages originate from
        fullFuncName = __name__ + '::runBenchmarks'
        indent = len(fullFuncName) + 2

        #setup and run each data set the specified number of iterations
        for dataSet in self.dataSets:
            #setup data set directory
            dataSetDir = self.workDir + dataSet + '-' + self.hostName + '/'
            if not os.path.isdir(dataSetDir):
                os.mkdir(dataSetDir)

            #setup machine_wrapping logs
            outString = fullFuncName + ': Beginning benchmark test(s) of ' + \
                        'data set "' + dataSet + '".\n' + ' '*indent + \
                        'Planning to run ' + \
                        str(self.jobs[dataSet]['nIters']) + ' iterations.'
            self.writeToWrappingLog(outString, quiet=self.quiet)

            #determine source of raw data
            params = getattr(parameters, dataSet)
            if self.jobs[dataSet]['skipDownload']:
                if not self.lustreAccess and 'Darwin' in self.os:
                    if self.jobs[dataSet]['step'] == 'cal':
                        dataPath = params['elric']['uncalData']
                    if self.jobs[dataSet]['step'] == 'im':
                        dataPath = params['elric']['calData']
                    if self.jobs[dataSet]['step'] == 'both':
                        dataPath = params['elric']['uncalData']
                else:
                    if self.jobs[dataSet]['step'] == 'cal':
                        dataPath = params['lustre']['uncalData']
                    if self.jobs[dataSet]['step'] == 'im':
                        dataPath = params['lustre']['calData']
                    if self.jobs[dataSet]['step'] == 'both':
                        dataPath = params['lustre']['uncalData']
            else:
                if self.jobs[dataSet]['step'] == 'cal':
                    dataPath = params['online']['uncalData']
                if self.jobs[dataSet]['step'] == 'im':
                    dataPath = params['online']['calData']
                if self.jobs[dataSet]['step'] == 'both':
                    dataPath = params['online']['uncalData']

            #determine source of scripts
            if self.jobs[dataSet]['scriptsSource'] == 'disk':
                if not self.lustreAccess and 'Darwin' in self.os:
                    calSource = params['elric']['calScript']
                    imSource = params['elric']['imScript']
                else:
                    calSource = params['lustre']['calScript']
                    imSource = params['lustre']['imScript']
            else:
                calSource = params['online']['calScript']
                imSource = params['online']['imScript']

            #actually run the benchmarks
            for i in range(self.jobs[dataSet]['nIters']):
                outString = fullFuncName + ': Beginning iteration ' + str(i)
                self.writeToWrappingLog(outString, quiet=self.quiet)

                b = benchmark.benchmark(scriptDir=self.scriptDir, \
                                 workDir=dataSetDir, \
                                 execStep=self.jobs[dataSet]['step'], \
                                 calSource=calSource, \
                                 imSource=imSource, \
                                 dataPath=dataPath, \
                                 skipDownload=self.jobs[dataSet]['skipDownload'],
                                 quiet=True)
                self.jobs[dataSet]['benchmarks'].append(b)

                if not self.jobs[dataSet]['skipDownload']:
                    b.downloadData()
                b.extractData()

                #try to only extract scripts once
                if self.jobs[dataSet]['benchmarks'][i-1].status == 'normal' and \
                   i != 0:
                    b.useOtherBmarkScripts(self.jobs[dataSet]['benchmarks'][i-1])
                else:
                    b.doScriptExtraction()
                if b.status == 'failure': continue

                b.runGuideScripts(CASAglobals=self._CASAglobals)

                if cleanUp:
                    b.emptyCurrentRedDir()
                    if not self.jobs[dataSet]['skipDownload']:
                        b.removeTarDir()

        outString = 'Finished benchmarking on ' + self.hostName + '.'
        self.writeToWrappingLog(outString, quiet=self.quiet)

    def writeToWrappingLog(self, outString, quiet):
        """Write outString to a text file named [hostname]_machine_wrapping.log.

        Parameters
        ----------
        outString : str
           String containing characters to be written to
           [hostname]_machine_wrapping.log.

        quiet : bool
           Switch determining if outString should be printed to the terminal.
           Defaults to the benchmark object's quiet instance variable (set when
           instantiating the object).

        Returns
        -------
        None

        Notes
        -----
        Write messages stored in outString to a text file named
        [hostname]_machine_wrapping.log in the machine directory. Optionally
        print outString to terminal too. These messages are from starting data
        set benchmarking and index of iteration executing.
        """
        #for telling where printed messages originate from
        fullFuncName = __name__ + '::writeToWrappingLog'
        indent = len(fullFuncName) + 2

        f = open(self.wrappingLog, 'a')
        f.write(outString+'\n')
        f.close()

        if not quiet:
            self._printAndFlush(outString)

    def _printAndFlush(self, outString):
        """Prints and then calls sys.stdout.flush().

        Returns
        -------
        None

        Parameters
        ----------
        outString : str
           String to be printed to sys.stdout.

        Notes
        -----
        This is a convenience function to make sure that sys.stdout.flush() is
        always called after a plain print statement. This ensures running
        benchmarking with Python's subprocess module writes everything to the
        proper location.
        """
        #for telling where printed messages originate from
        fullFuncName = __name__ + '::_printAndFlush'
        indent = len(fullFuncName) + 2

        print outString
        sys.stdout.flush()
