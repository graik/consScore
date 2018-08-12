#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jun 26 09:45:57 2018

@author: suliat16
"""

import os
import re
import tempfile
import warnings
import numpy as np
import biskit.tools as t
from Bio.Align.Applications import TCoffeeCommandline
from biskit.exe import Executor
from biskit.errors import BiskitError

class SequenceError(BiskitError):
    pass

class Rate4SiteError(BiskitError):
    pass

def build_alignment(file):
    """
    Calls the TCoffee program to build an alignment of protein sequences
    Args:
        file: The absolute file path to the collection of protein sequences
    Returns:

    """
    tcoffee_cline = TCoffeeCommandline(infile=file,
                                       output='clustalw',
                                       outfile='%s' %(os.path.basename(file)))
    directory = tempfile.mkdtemp()
    os.chdir(directory)
    tcoffee_cline()
    return directory
    #TODO: cleanup method has to change back the working directory
    

class Rate4Site(Executor):

    """
    Wraps the Rate4Site program. Calling run() executes the program, which creates
    a folder containing the rate4site output information and the tree, and returns
    an array that maps the data onto each amino acid, which by default is the
    conservation score.

    Rate4Site is used for academic purposes. Citation:
    Mayrose, I., Graur, D., Ben-Tal, N., and Pupko, T. 2004. Comparison of
    site-specific rate-inference methods: Bayesian methods are superior.Mol Biol
    Evol 21: 1781-1791.
    """

    def __init__(self, msa, *args, cwdir=None, **kw):

        aln_file = os.path.basename(msa)
        self.dir_name = aln_file.split('.')[0]
        super().__init__(name='rate4site', args='-s %s -o %s.res'% (msa, self.dir_name),
                         catch_out=1, **kw, tempdir=self.dir_name)
        self.alpha = 0
        if not cwdir:
            self.cwd = os.getcwd() + os.sep + self.dir_name
        else:
            self.cwd = cwdir
        self.score_output = self.cwd + os.sep + '%s.res'% self.dir_name
        self.keep_tempdir = True
        self.has_run = False


    def run(self):
        """
        Calls the executor run method if it is a first run, otherwise just calls
        the post execution methods on the cached files
        """
        if self.has_run:
            self.finish()
            return self.result
        else:
            return super().run()


    def finish(self):
        """
        Overwrites Executor method. Called when the program is done executing.
        """
        super().finish()
        self.alpha = self.get_alpha(self.score_output)
        self.result = self.read2matrix(self.score_output)
        self.keep_tempdir = True
        self.has_run = True

    def isfailed(self):
        """
        Overwrites Executor method. Return True if the external program has finished
        successfully, False otherwise
        """
        ret = None
        if self.returncode == 0:
            ret = False
        else:
            ret = True
        return ret

    def fail(self):
        """
        Overwrites Executor method. Called if external program has failed
        """
        s = 'Rate4Site failed. Please check the program output in the '+\
            'field `output` of this Rate4Site instance, (eg. `print x.output`)!'
        self.log.add(s)
        raise Rate4SiteError(s)

    def cleanup(self):
        """
        Overwrites Executor method. Cleans up files created during program execution.
        """
        #t.tryRemove(self.cwd + os.sep + 'TheTree.txt')
        t.tryRemove(self.cwd + os.sep + 'r4s.res')
        t.tryRemove(self.cwd + os.sep + 'r4sOrig.res')
        super().cleanup()

    def close(self):
        """
        Deletes the output files of rate4site- the alignment tree and the score
        sheet.
        """
        t.tryRemove(self.cwd + os.sep + 'TheTree.txt')
        t.tryRemove(self.tempdir, tree=True)
        self.has_run = False

    def __del__(self):
        """
        Deletes output files for rate4stie. When called by garbage collector it also
        deletes the rate4site instance
        """
        t.tryRemove(self.cwd + os.sep + 'TheTree.txt')
        t.tryRemove(self.tempdir, tree=True)

    @classmethod
    def get_alpha(cls, r4s):
        """
        Get the alpha parameter of the conservation scores
        Args:
            r4s (file): The absolute file path to the alignment file
        Returns:
            The alpha parameter of the conservation score.
        """
        try:
            if os.path.isfile(r4s):
                with open(r4s, 'r') as f:
                    contents = f.read()
                splitted = contents.split(os.linesep)
                for s in splitted:
                    if re.search('alpha parameter', s):
                        parameter = s
                        parameter = Rate4Site.get_num(parameter)
                        return parameter[0]
            else: 
                raise FileNotFoundError
        except IndexError:
            raise Rate4SiteError('File format is not supported')
        finally:
            warnings.warn("This method is especially susceptible to changes in the format of \
            the output file", Warning)

    @classmethod
    def get_num(cls, string):
        """
        Takes a string and returns the first number in that string, decimal included
        Args:
            string(str): The string containing a number
        Returns:
            A list of all the numbers contained in that string, as floats
        """
        digits = r"-?[0-9]*\.?[0-9]+"
        parameter = re.findall(digits, string)
        return list(map(float, parameter))

    @classmethod
    def read2matrix(cls, r4s, identity=True, score=True, qqint=False, std=False,
                    msa=False):
        """
        Take the output from rate4site and convert it into a numpy array, mapping
        each conservation score onto its corresponding amino acid.

        Args:
            file: The output from the Rate4Site program, version 2.01
        Returns:
            An array, where the entry at each index contains information about
            the amino acid at that position.

        The document is parsed by pulling splitting the text from the output file
        using newlines as delimiters, and grabbing only the lines that do not start
        with a # symbol. Whats left are the rows of the table, where each row contains
        information about an amino acid. The rows are then split up depending on
        what information it carries.
        """
        try:
            if os.path.isfile(r4s):
                with open(r4s, 'r') as file:
                    contents = file.read()
                residues = Rate4Site.extract_resi(contents)
                func_args = [identity, score, qqint, std, msa]
                dimension = func_args.count(True)
                r2mat = np.empty([1, dimension])
                for r in residues:
                    np_residues = np.array([])
                    if identity:
                        amino = r.split()[1]
                        np_residues = np.append(np_residues, amino)
                    if score:
                        conse = r.split()[2]
                        np_residues = np.append(np_residues, conse)
                    if qqint:
                        intqq = r.split("")[3]
                        np_residues = np.append(np_residues, intqq)
                    if std:
                        stdev = r.split()[4]
                        np_residues = np.append(np_residues, stdev)
                    if msa:
                        align = r.split()[5]
                        np_residues = np.append(np_residues, align)
                    np_residues = np_residues.reshape((1, dimension))
                    r2mat = np.concatenate((r2mat, np_residues), axis=0)
                r2mat = np.delete(r2mat, 0, axis=0)
                return r2mat
            else:
                raise FileNotFoundError
        finally:
            warnings.warn("This method is especially susceptible to changes in the format of \
            the output file", Warning)

    @classmethod
    def extract_resi(cls, string):
        """
        Grabs the lines of the table that correspond to amino acid data, and puts
        them in a list.
        Args:
            string(str): The contents of the rate4site file
        Returns:
            The rows of the amino acid table as a list of strings.
        """
        splitted = string.split(os.linesep)
        residues = []
        for s in splitted:
            #Remove comments and empty lines
            if s is not '' and not s.startswith('#'):
                #Remove comments
                residues.append(s)
        return residues
