#!/usr/bin/env python
# Copyright (C) 2018 Prayush Kumar
#
# =============================================================================
#
#                                   Preamble
#
# =============================================================================
#
import os
import sys
import h5py

import commands as cmd
import string
from numpy import *
import numpy as np
from numpy.random import random

from scipy.interpolate import interp1d, InterpolatedUnivariateSpline
from scipy.misc import derivative
from scipy.optimize import bisect, brentq, minimize_scalar
from scipy.integrate import simps, cumtrapz

import lal
from pycbc.waveform import *
from pycbc.types import *
from pycbc.filter import *
from pycbc.psd import from_string

from GWNRTools.NR.DataContainers import nr_data
from GWNRTools.NR.SingleMode import nr_mode
from GWNRTools.Utils import get_time_at_frequency, zero_pad_beginning
######################################################################
__author__   = "Prayush Kumar <prayush@astro.cornell.edu>"
PROGRAM_NAME = os.path.abspath(sys.argv[0])
verbose      = False




## @nr_wave pyexample
#  Documentation for this module.
#
## Alias "nr_wave" to "nr_strain". This way we have a complete set of
## - "nr_data" as raw data containers for NR data
## - "nr_mode" as manipulation class for single NR modes
## - "nr_strain" / "nr_wave" as manipulation class for GW strain
## Each class depends on the all previous ones.
#
######################################################################
######################################################################
#
#     Make a class for basic manipulations of SpEC NR waveforms      #
#
######################################################################
######################################################################
class nr_strain():
    #{{{
    def __init__(self,
                 filename,\
                 filetype='HDF5',\
                 wavetype='Auto', \
                 wave_uniformly_sampled=False,\
                 ex_order = 3,\
                 group_name = None,\
                 modeLmin = 2,\
                 modeLmax = 4,\
                 skipM0 = True,\
                 which_modes = [],\
                 dimless_sample_rate=1.0,\
                 sample_rate=4096,\
                 time_length=16,\
                 totalmass=None,\
                 inclination=0.0,\
                 phi=0.0,\
                 distance=1.0e6,\
                 verbose=0):
        """
##################################################
######        ASSUMPTIONS
##################################################
### 1: All modes share a common time stencil

##################################################
######        CONVENTIONS
##################################################
### 1: Modes themselves are not amplitude-scaled. Only their time-axis is
###    rescaled.
### 2: Following <https://arxiv.org/pdf/0709.0093.pdf> we will follow the convention where:
###
### $$h_+ - i h_\times = \sum_{l,m} Y^{l,m}_{-2}(\iota, \phi_c) h_{l,m}(M_i, S_i, \cdots)$$
###
### and each *(l,m)* multipole is expanded in amplitude and phase as:
###
### $$h_{l,m} := A_{l,m} \mathrm{e}^{i\phi_{l,m}}$$
###
### where $$\phi_{l,m}\propto -m\times\Phi (=\phi_\mathrm{orbital})$$,
###
### i.e. $$h_{l,m} := A_{l,m} \mathrm{e}^{-i m\Phi}$$, and
###
### $$\mathcal{Re}[h_{l,m}] := +A_{l,m} \cos(m\Phi)$$
### $$\mathcal{Im}[h_{l,m}] := -A_{l,m} \sin(m\Phi)$$
###

##################################################
###           INPUTS
##################################################
### 1: filename = FULL PATH to NR data file

### 2: filetypes passed should be : 'HDF5' , 'ASCII' or 'DataSet'
#### 2.1: For HDF5 files:-
#### Between "wavetype", "ex_order", and "group_name", provide:
           a) for CCE waveforms, wavetype=CCE. It uses highest-R data.
           b) for extrapolated waveforms, wavetype='Extrapolated' and ex_order=?
           c) for finite-radii waveforms, wavetype='FiniteRadius'
           d) for datasets without groups, wavetype='NoGroup'
           e) (experimental) Determine automatically: wavetype='Auto' (default)
           f) for non-SXS waveforms, group_name='...'
    Note: group_name overwrites other two options. So one can also provide
                group_name = 'Extrapolated_N3.dir' OR
                group_name = 'CceR0350.dir', etc.
#### 2.2: For ASCII files:-
####  () Provide wavetype = 'regex'. This assumes:
           a) filename is a REGEX expression that can be formatted with (modeL, modeM) integer tuples
#### 2.3: For DataSet:-
####  () Provide wavetype = 'dict'. This assumes:
           a) This dictionary should have [l][m] modes as Nx2 or Nx3 matrices

### 6: modeLmin, modeLmax: Range of l-modes of strain to use
            (cannot use arbitrary ones yet)
### 7: skipM0: Skip m=0 (DC) modes (Default: True)
### 8: sample_rate, time_length: length params for data structures
### 9: dimless_sample_rate: length params in dimensionless units
### 10: totalmass: total mass to rescale NR waveform to (Solar Masses)
### 11: inclination, phi: Inclination and initial phase angles (rad)
### 12: distance: distance to source (Pc, Default=1e6 or 1Mpc)

        """
        self.verbose = verbose
        ##################################################################
        #   0. Ensure inputs are correct
        ##################################################################
        if 'DataSet' not in filetype:
            if filename is not None and not os.path.exists(filename):
                raise IOError("Please provide data file!")
            if self.verbose > 0:
                print "Init nr_wave: Reading From Filename=%s" % filename
        ##################################################################
        # 1. Store various things
        ##################################################################
        # Datafile details
        self.modeLmax = modeLmax
        self.modeLmin = modeLmin
        self.skipM0   = skipM0
        self.which_modes = which_modes

        # Binary parameters
        self.totalmass = totalmass
        if self.totalmass:
            self.totalmass_secs = self.totalmass * lal.MTSUN_SI
        self.inclination = inclination
        self.phi = phi
        self.distance = distance
        if self.verbose > 2:
            print "\t\tInput mass, inc, phi, dist = ", totalmass,\
                                self.inclination, self.phi, self.distance

        # Data analysis parameters
        self.sample_rate = sample_rate
        self.time_length = time_length
        self.delta_t = 1./self.sample_rate
        self.dimless_delta_t = 1.0 / dimless_sample_rate
        self.df = 1./self.time_length
        self.n = int(self.sample_rate * self.time_length)
        if self.verbose > 1:
            print "self.sample-rate & time_len = ", self.sample_rate, self.time_length
            print "self.n = ", self.n

        ##################################################################
        #   2. Read the data from the file. Read all modes.
        ##################################################################
        if self.verbose > 1:
            print "Init nr_wave: Reading data...."
        self.data = nr_data(filename, filetype=filetype, wavetype=wavetype,
                            ex_order=ex_order, group_name=group_name,
                            modeLmin = self.modeLmin, modeLmax = self.modeLmax,
                            skipM0 = self.skipM0,
                            delta_t = 1.0 / dimless_sample_rate,
                            verbose = self.verbose)
        self.which_modes_to_read()
        self.rescaled_hp, self.rescaled_hc = None, None
        if self.verbose > 1:
            print "Init nr_wave: Data reading successful."
            if self.verbose > 2: print "\t\t Read in modes: ", self.which_modes
        ##################################################################
        #   3. Preprocessing
        ##################################################################
        ## self.rescale_modes()
        if self.totalmass > 1.0: self.rescale_to_totalmass(self.totalmass)
        if self.verbose > 1:
            print "Init nr_wave: Successful."
        return
    ##
    def which_modes_to_read(self):
        if len(self.which_modes) == 0:
            for modeL in self.data.modes:
                for modeM in self.data.modes[modeL]:
                    self.which_modes.append( (modeL, modeM) )
        return self.which_modes
    ##
    ####################################################################
    ####################################################################
    ##### Functions to operate on individual modes
    ####################################################################
    ####################################################################
    #
    # Read mode amplitude as a function of t (in s or M)
    def get_mode_amplitude(self, modeL=2, modeM=2, startIdx=0, stopIdx=-1, dimensionless=False):
        """ compute the amplitude of a given mode. If dimensionless amplitude as a
        function of dimensionless time is not needed, make sure totalmass is set
        either in this function, or in the object earlier.
        """
        if dimensionless: self.make_modes_dimensionless()
        return self.data.modes[modeL][modeM].amplitude(startIdx=startIdx, stopIdx=stopIdx)
    #
    # Returns frequency (in Hz or 1/M) as a function of t (in s or M)
    def get_mode_frequency(self, modeL=2, modeM=2, startIdx=0, stopIdx=-1, dimensionless=False):
        if dimensionless: self.make_modes_dimensionless()
        return self.data.modes[modeL][modeM].frequency(startIdx=startIdx, stopIdx=stopIdx)
    #
    # Returns MODE PHASE (in radians) as a function of t (in s or M)
    def get_mode_phase(self, modeL=2, modeM=2, startIdx=0, stopIdx=-1, dimensionless=False):
        if dimensionless: self.make_modes_dimensionless()
        return self.data.modes[modeL][modeM].phase(startIdx=startIdx, stopIdx=stopIdx)
    #
    ####################################################################
    # Functions related to wave-frequency
    ####################################################################
    #
    def get_t_frequency(self, f, totalmass=None, dimless=False):
        """
Provide f (frequency) in Hz. Or provide f (dimension-less) if dimless=True.
Returns t (time) in seconds. Or returns t (dimension-less) if dimless=True.
        """
        if f < 1.0:
            f_is_dimless = True
        else:
            f_is_dimless = False
        ##
        if totalmass is None:
            totalmass = self.totalmass
        #else:
        #    self.totalmass = totalmass
        #    self.rescale_modes(M=totalmass)

        ##
        ## Get frequency timeSeries for the (2,2) mode
        freq = self.get_mode_frequency(modeL=2, modeM=2)

        ## Find time and use correct units
        if self.data.modes[2][2].dimLess:
            if not f_is_dimless and totalmass is None:
                raise IOError("Since you haven't rescaled this wave yet, provide dimensionless frequency instead of {}".format(f))
            elif not f_is_dimless:
                f *= (totalmass * lal.MTSUN_SI) # Make frequency dimensionless
            t = get_time_at_frequency(freq, f)  # This will give dimensionless time
            if not dimless and totalmass != None:
                t *= (totalmass * lal.MTSUN_SI)
        else:
            if f_is_dimless:
                f /= (totalmass * lal.MTSUN_SI)
            t = get_time_at_frequency(freq, f) # This will be time in seconds
            if dimless:
                t /= (totalmass * lal.MTSUN_SI)
        return t
    #
    # Get 2,2-mode GW_frequency in Hz at a given time (M)
    #
    def get_frequency_t(self, t, totalmass=None, dimless=False):
        """
Get 2,2-mode GW_frequency in Hz at a given time (in M)
        """
        if totalmass is None:
            totalmass = self.totalmass
        #else:
        #    self.totalmass = totalmass
        #    self.rescale_to_totalmass(totalmass)

        freq = self.get_mode_frequency(modeL=2, modeM=2)
        freqI = InterpolatedUnivariateSpline(freq.sample_times, freq)

        f_is_dimless = self.data.modes[2][2].dimLess

        # If requested operation uses dimensionless Units, we
        # assume the t given is in units of M, and
        if f_is_dimless:
            # Convert t if its in seconds
            if totalmass is not None:
                t /= (totalmass * lal.MTSUN_SI)
            else:
                #raise IOError("Please provide totalmass to convert time to dimenLess Units")
                pass
        else:
            # Assume now the time given t is in seconds
            pass

        try:
            fvalue = freqI(t)
        except:
            raise IOError("""
            Time provided = {} and times of frequencyTimeSEries: {},{}
            Request to use Dimless Units: {}.
            Are these consistent?
            """.format(t, freq.sample_times[0], freq.sample_times[-1], dimless))

        if self.verbose > 1:
            print "\tget_frequency_t: t = {}, freq = {}".format(t, fvalue)

        return fvalue

    ###################################################################
    # Functions related to wave-amplitude
    ###################################################################
    #
    # Get the 2,2-mode GW amplitude at the peak of |h22|
    def get_amplitude_peak_h22(self, amp=None):
        """ Get the 2,2-mode GW amplitude at the peak of |h22|. """
        if amp is None:
            amp = self.data.modes[2][2].amplitude()
        iMax = np.where(np.abs(amp.sample_times.data) == np.min(np.abs(amp.sample_times.data)))[0][0]
        aMax = amp[iMax]
        return [aMax, iMax]
    #
    # Get the amplitude of + x polarizations
    def amplitude(self):
        if self.rescaled_hp is None or self.rescaled_hc is None:
            raise IOError("Please call `get_polarizations` first. ")
        #return np.abs(self.rescaled_hp**2 + self.rescaled_hc**2)**0.5
        return amplitude_from_polarizations(self.rescaled_hp, self.rescaled_hc)
    #
    # Get the phase of + x polarizations
    def phase(self):
        if self.rescaled_hp is None or self.rescaled_hc is None:
            raise IOError("Please call `get_polarizations` first. ")
        return phase_from_polarizations(self.rescaled_hp, self.rescaled_hc)
    #
    # Get the frequency of + x polarizations
    def frequency(self):
        if self.rescaled_hp is None or self.rescaled_hc is None:
            raise IOError("Please call `get_polarizations` first. ")
        return frequency_from_polarizations(self.rescaled_hp, self.rescaled_hc)
    # ##################################################################
    # Basic waveform manipulation
    # ##################################################################
    ##
    def make_modes_dimensionless(self, dimless_delta_t=-1):
        if dimless_delta_t < 0: dimless_delta_t = self.dimless_delta_t
        _ = self.which_modes_to_read()
        for (modeL, modeM) in self.which_modes:
            self.data.modes[modeL][modeM].resample(dimless_delta_t)
        self.totalmass = None
        self.rescaled_hp = None
        self.rescaled_hc = None
        return self
    ##
    def rescale_modes(self, delta_t=None, M=None, distance=None):
        """
        This function rescales ALL modes to input mass value.
        This function is meant for usage in amplitude-scaling-invariant calculations.

        Note that this function RESETS internal total-mass values for all modes
        consistently
        """
        ##{{{
        if delta_t is None: delta_t = self.delta_t
        else: self.delta_t = delta_t

        if M is None: M = self.totalmass
        else: self.totalmass = M

        if distance is None: distance = self.distance
        else: self.distance = distance

        if self.verbose > 1:
            print "\tRescaling modes to: delta_t={}, M={}, dist={}".format(delta_t, M, distance)

        if delta_t is None or M is None or distance is None:
            raise IOError("One of delta_t={}, M={}, dist={} is None.\
            Please provide valid parameters to rescale modes".format(delta_t, M, distance))

        which_modes = self.which_modes_to_read()
        if self.verbose > 2:
            print "\t\tWill use modes: ", which_modes

        for (modeL, modeM) in which_modes:
            self.data.modes[modeL][modeM].resample_to_Hz(delta_t,
                                                         M,
                                                         distance = distance)
        return
        ##}}}
    ##
    def get_polarizations(self, delta_t=None, M=None, distance=None, inclination=None, phi=None):
        """
Return plus and cross polarizations.
        """
        ##{{{
        #########################################################
        #### INPUT CHECKING
        #########################################################
        if delta_t is None: delta_t = self.delta_t
        else: self.delta_t = delta_t

        if M is None: M = self.totalmass
        else: self.totalmass = M

        if distance is None: distance = self.distance
        else: self.distance = distance

        if phi is None: phi = self.phi
        else: self.phi = phi

        if inclination is None: inclination = self.inclination
        else: self.inclination = inclination

        if delta_t is None or M is None or distance is None or inclination is None or phi is None:
            raise IOError("One of delta_t={}, M={}, dist={}, incl={}, phi={} is None.\
            Please provide valid parameters to obtain polarizations".format(delta_t,
                                                                            M,
                                                                            distance,
                                                                            inclination,
                                                                            phi))
        if self.verbose > 1:
            print "\tComputing polarizations for: delta_t={}, M={}, dist={}, incl={}, phi={}".format(\
                        delta_t, M, distance, inclination, phi)
        #########################################################
        #### RESCALE AND RESAMPLE INDIVIDUAL MODES
        #########################################################
        # First rescale all modes to required physical parameters
        self.rescale_modes(delta_t = delta_t, M = M, distance = distance)

        #########################################################
        #### ENSURE CORRECTNESS OF COALESCENCE-PHASE !!!!
        #########################################################
        # Orbital phase at the time of merger (time of amplitude peak for (2,2) mode)
        aPeak, iPeak = self.get_amplitude_peak_h22()
        if self.verbose > 3:
            print "\t\t\tFound peak of amplitude of h22 at (index, ampl): {}, {}".format(iPeak, aPeak)
        phase22 = self.get_mode_phase(2, 2)
        #phiOrbMerger = phase22[iPeak] / 2.
        phiOrbMerger = np.angle(self.data.modes[2][2].data()[iPeak])/-2

        #########################################################
        #### COMBINE MODES TO GET POLARIZATIONS
        #########################################################
        # Create an empty complex array for (+ , x) polarizations
        hpols = TimeSeries(np.zeros(self.n, dtype=float) + np.zeros(self.n, dtype=float) * 1.0j,
                           delta_t = delta_t,
                           epoch = phase22._epoch)
        curr_h22 = self.data.modes[2][2].data()
        # Loop over all modes to be included
        for (modeL, modeM) in self.which_modes_to_read():
            if self.skipM0 and modeM==0: continue
            #phiOrbMerger = np.angle(self.data.modes[modeL][modeM].data()[iPeak]) * (1.0 / modeM) ## FIXME!!
            #print type(hpols), hpols.dtype
            # Compute spin -2 weighted Ylm for (inclination, PHI??)
            curr_ylm_lal = lal.SpinWeightedSphericalHarmonic(inclination,
                                                             phiOrbMerger - 0*np.pi/4. - phi,
                                                             #phiOrbMerger  - phi,
                                                             -2,
                                                             modeL, modeM)
            #print type(curr_ylm_lal)
            curr_ylm = np.complex128(curr_ylm_lal.real + curr_ylm_lal.imag * 1.0j)
            #print np.abs(curr_ylm)
            #print "Difference: {}",format(np.abs(curr_ylm_lal - curr_ylm))

            # h+ - \ii hx = \Sum Ylm * hlm
            tmp_hlm = self.data.modes[modeL][modeM].data()
            ## FIXME DELME
            null_ylm = np.exp(-1 * (phiOrbMerger - 0*np.pi/4. - phi) * modeM * 1.0j)
            if True:
                print "\t\t\tPhaseRemovalTerm: ", null_ylm, null_ylm/np.abs(null_ylm)
                print "\t\t\tUSENR mode at peak: {}, after removing phase: {} ({})".format(tmp_hlm[iPeak],
                                                                    null_ylm * tmp_hlm[iPeak],
                                                                  np.angle(null_ylm * tmp_hlm[iPeak]) )

            curr_hlm = TimeSeries(tmp_hlm * curr_ylm,
                                  epoch=curr_h22._epoch,
                                  dtype=hpols.dtype,
                                  copy=True)
            if self.verbose > 1:
                print "\tShifted ({},{}) in time by {} units ({} samples)".format(
                    modeL, modeM, float(curr_hlm._epoch - tmp_hlm._epoch),
                    float(curr_hlm._epoch - tmp_hlm._epoch)/curr_hlm.delta_t)
            hpols[:len(curr_hlm)] += curr_hlm
        # h+ - \ii hx = \Sum Ylm * hlm
        self.rescaled_hp = TimeSeries(   hpols.real(), delta_t=hpols.delta_t, epoch=hpols._epoch)
        self.rescaled_hc = TimeSeries(-1*hpols.imag(), delta_t=hpols.delta_t, epoch=hpols._epoch)
        # Return polarizations
        return [self.rescaled_hp, self.rescaled_hc]
        ##}}}
    ##
    def rescale_to_totalmass(self, M):
        """ Rescales the waveform to a different total-mass than currently. The
        values for different angles are set to internal values provided earlier, e.g.
        during object initialization.
        """
        ##{{{
        if not hasattr(self, 'inclination') or self.inclination is None:
            raise RuntimeError("Cannot rescale total-mass without setting inclination")
        elif not hasattr(self, 'phi') or self.phi is None:
            raise RuntimeError("Cannot rescale total-mass without setting phi")
        elif not hasattr(self, 'distance') or self.distance is None:
            raise RuntimeError("Cannot rescale total-mass without setting distance")
        return self.get_polarizations(M=M,
                                      inclination=self.inclination,
                                      phi=self.phi,
                                      distance=self.distance)
        ##}}}
    ##
    def rescale_to_distance(self, distance):
        """ Rescales the waveform to a different distance than currently. The
        values for different angles, masses are set to internal values provided
        earlier, e.g. during object initialization.
        """
        ##{{{
        if not hasattr(self, 'inclination') or self.inclination is None:
            raise RuntimeError("Cannot rescale distance without setting inclination")
        elif not hasattr(self, 'phi') or self.phi is None:
            raise RuntimeError("Cannot rescale distance without setting phi")
        elif not hasattr(self, 'totalmass') or self.totalmass is None:
            raise RuntimeError("Cannot rescale distance without setting total-mass")
        return self.get_polarizations(M=self.totalmass,
                                      inclination=self.inclination,
                                      phi=self.phi,
                                      distance=distance)
        ##}}}
    ##
    def rotate(self, inclination=None, phi=None):
        """ Rotates waveforms to different inclination and initial-phase angles,
        with the total-mass and distance set to internal values, provided earlier,
        e.g. during object initialization.
        """
        ##{{{
        if not hasattr(self, 'totalmass') or self.totalmass is None:
            raise RuntimeError("Cannot rotate without setting total mass")
        elif not hasattr(self, 'distance') or self.distance is None:
            raise RuntimeError("Cannot rescale total-mass without setting distance")
        if inclination is None: inclination = self.inclination
        else: self.inclination = inclination
        if phi is None: phi = self.phi
        else: self.phi = phi
        return self.get_polarizations(M=self.totalmass,
                                      inclination=inclination,
                                      phi=phi,
                                      distance=self.distance)
        ##}}}
    ##
    ####################################################################
    ####################################################################
    ##### Functions to operate on polarizations
    ####################################################################
    ####################################################################
    #
    def get_lowest_binary_mass(self, f_lower, t_start, totalmass=None, dimless=True):
        """
Gives the Lowest possible binary total mass that the waveform can/should be
scaled to to start at **f_lower** at the time-sample at **t_start**

Choose t_start after Junk

f_lower can be in Hz of 1/M

t_start is dimensionless IFF dimless = True, else its in seconds
[MERGER is at t=0]
        """
        ##{{{
        if totalmass is None:
            totalmass = self.totalmass

        UNDO_SCALING = False
        if totalmass is None:
            totalmass = 40.0
            self.rescale_to_totalmass(totalmass)
            self.totalmass = totalmass
            UNDO_SCALING = True

        if dimless:
            t_start *= (totalmass * lal.MTSUN_SI)

        orbit_freq = self.get_frequency_t(t_start, totalmass=totalmass, dimless=False)

        if f_lower < 1.0:
            f_lower /= (totalmass * lal.MTSUN_SI)

        if self.verbose > 1:
            print "\t orbit_freq found: {}, f_lower = {}".format(orbit_freq, f_lower)

        if UNDO_SCALING:
            if self.verbose > 0:
                print "WARNING: Waveform has been rescaled to M={}".format(totalmass)
        ##
        return (orbit_freq / f_lower) * totalmass
        ##}}}
    ###################################################################
    ####################################################################
    # Strain conditioning
    ####################################################################
    ###################################################################
    #
    def taper_filter_waveform(self,
                              hpsamp=None, hcsamp=None, totalmass=None,\
                              tapermethod='planck', \
                              ttaper1=100,\
                              ttaper2=1000,\
                              ftaper3=0.1,\
                              ttaper4=100.,\
                              npad=0, f_filter=-1.):
        """
Tapers using a Plank-taper window and high-pass filters.
**IMPORTANT** The domain of the window is passed as ttaper{1,2,3,4} values.

    ttaper1 : time (in total-mass units) from the start where the window starts
    ttaper2 : width of start window
    ftaper3 : fraction by which amplitude should fall after its peak,
                    marking where the rolldown window starts
    ttaper4 : width of the rolldown window

Currently supported tapermethods: 'planck' [default], 'cosine'
        """
        #{{{
        ## Choose polarizations: Either User inputs here or use the objects internal polz.
        if hpsamp and hcsamp:
            hp0, hc0 = [hpsamp, hcsamp]
            if totalmass is None: raise IOError("If providing polarizations, also provide total mass!")
        elif self.rescaled_hp is not None and self.rescaled_hc is not None:
            totalmass = self.totalmass
            hp0, hc0 = self.rescaled_hp, self.rescaled_hc
        else: raise IOError("Please call `get_polarizations` first. Or provide polarizations as input.")

        ## Check windowing extents
        if (ttaper1+ttaper2+ttaper4) > (len(hp0)*hp0.delta_t/self.totalmass/lal.MTSUN_SI):
            raise IOError("Invalid window configuration with [%f,%f,%f,%f] for wave of length %fM" %\
                            (ttaper1, ttaper2, ftaper3, ttaper4, (len(hp0)*hp0.delta_t/self.totalmass/lal.MTSUN_SI)))

        ## Copy over polarizations to fresh memory
        hp = TimeSeries( hp0.data, dtype=hp0.dtype, delta_t=hp0.delta_t, epoch=hp0._epoch, copy=True )
        hc = TimeSeries( hc0.data, dtype=hc0.dtype, delta_t=hc0.delta_t, epoch=hc0._epoch, copy=True )

        ## Get actual waveform length (minus padding at the end)
        N = np.minimum(np.where(hp.data == 0)[0][0], np.where(hc.data == 0)[0][0])

        ## Check if npad can be inserted at the start of the polarization TimeSeries.
        ## If there is no space ignore the pad completely
        if abs(len(hp) - N) < npad:
            print "WARNING: Cannot pad {} zeros at the end. len(hp)={} & N={}".format(npad,len(hp),N)
            npad = 0
        else:
            # Prepend some zeros to the waveform (assuming there are ''npad'' zeros at the end)
            hp = zero_pad_beginning( hp, steps=npad )
            hc = zero_pad_beginning( hc, steps=npad )

        ##########################################################
        # ########   Construct the taper window configuration ####
        ##########################################################
        # Get the amplitude peak
        amp = amplitude_from_polarizations(hp, hc)
        # N + npad == total length
        # start from 0.8 * (N + npad)
        iStart = int(0.8 * (N + npad))
        max_a, nPeak = amp[iStart:].abs_max_loc()
        nPeak += iStart

        # First get the starting-half indices
        ttapers = np.array([ttaper1, ttaper2], dtype=np.float128)
        ntaper1, ntaper2 = np.int64( np.round(ttapers * totalmass * lal.MTSUN_SI / hp.delta_t) )
        ntaper2 += ntaper1

        if ntaper2 < ntaper1:
            raise RuntimeError("Could not configure starting taper-window")

        ## Get the itime/index where the polarization amplitude = `ftaper3` x peakAmplitude
        amp_after_peak = amp[nPeak:]
        iA, vA = min(enumerate(amp_after_peak),key=lambda x:abs(x[1] - ftaper3*max_a))
        ntaper3 = nPeak + iA
        #iB, vB = min(enumerate(amp_after_peak),key=lambda x:abs(x[1] - 0.01*max_a))
        #iB = iA + ntaper4

        ## End of RD window is given by `width=ttaper4` + `start = ntaper3`
        ntaper4 = ntaper3
        ntaper4 += np.int64(\
              np.round(ttaper4 * totalmass * lal.MTSUN_SI / hp.delta_t))

        ## If the above minimization to find the RD window fails, try brute force!
        if ntaper3 <= nPeak or ntaper4 < ntaper3:
            tmp_data = amp_after_peak.data
            for idx in range( len(amp_after_peak) ):
                if tmp_data[idx] < ftaper3*max_a: break
            ntaper3 = nPeak + idx
            for idx in range( len(amp_after_peak) ):
                if tmp_data[idx] < ftaper4*max_a: break
            ntaper4 = nPeak + idx

        ## If the RD window is STILL NOT CONFIGURED, FAIL!
        if ntaper3 <= nPeak or ntaper4 < ntaper3 or ntaper3 < ntaper2 or ntaper2 < ntaper1:
            raise RuntimeError("Could not configure ringdown tapering window: {},{},{},{}".format(
                  ntaper1, ntaper2, ntaper3, ntaper4))

        #######################################################################
        # ################  Make final tapering window ########################
        #######################################################################
        # NOTE: ntaper1, ntaper2, ntaper3, ntaper4 are all measured    ########
        #        w.r.t. the start of hp, instead of w.r.t. each other. ########
        #######################################################################
        #
        # Combine window configuration
        ntapers = np.array([ntaper1, ntaper2, ntaper3, ntaper4], dtype=np.int64)
        ttapers = np.float128(ntapers) * hp.delta_t
        time_array = hp.sample_times.data - np.float(hp._epoch)

        if self.verbose > 2:
            print "ntapers = ", ntapers
            print "ttapers = ", ttapers
        #
        # Windowing function time-series
        #
        region1 = np.zeros(ntaper1)
        region2 = np.zeros(ntaper2 - ntaper1) ## Modified later to chosen taperfunction
        region3 = np.ones(ntaper3 - ntaper2)
        region4 = np.zeros(ntaper4 - ntaper3) ## Modified later to chosen taperfunction
        region5 = np.zeros(len(hp) - ntaper4)
        #
        ## Modify region2 and region3 to chosen taperfunction
        if 'planck' in tapermethod:
            np.seterr(divide='raise',over='raise',under='ignore',invalid='raise')
            t1, t2, t3, t4 = ttapers
            i1, i2, i3, i4 = ntapers
            if self.verbose > 2:
                print "\t\twindow times = ", t1, t2, t3, t4
                print "\t\tidxs = ", i1, i2, i3, i4
            #
            for i in range(len(region2)):
                if i == 0:
                    region2[i] = 0
                    continue
                try:
                    region2[i] = 1./(np.exp( ((t2-t1)/(time_array[i+i1]-t1)) + \
                                      ((t2-t1)/(time_array[i+i1]-t2)) ) + 1)
                except:
                    if time_array[i+i1]>0.9*t1 and time_array[i+i1]<1.1*t1: region2[i] = 0
                    if time_array[i+i1]>0.9*t2 and time_array[i+i1]<1.1*t2: region2[i] = 1.
            #
            for i in range(len(region4)):
                if i == 0:
                    region4[i] = 1.
                    continue
                try:
                    region4[i] = 1./(np.exp( ((t3-t4)/(time_array[i+i3]-t3)) + \
                                      ((t3-t4)/(time_array[i+i3]-t4)) ) + 1)
                except:
                    if time_array[i+i3]>0.9*t3 and time_array[i+i3]<1.1*t3: region4[i] = 1.
                    if time_array[i+i3]>0.9*t4 and time_array[i+i3]<1.1*t4: region4[i] = 0
            #
            if self.verbose > 3:
                import matplotlib.pyplot as plt
                plt.plot(np.arange(len(region1))*hp.delta_t, region1)
                offset = len(region1)
                plt.plot((offset+np.arange(len(region2)))*hp.delta_t, region2)
                offset += len(region2)
                plt.plot((offset+np.arange(len(region3)))*hp.delta_t, region3)
                offset += len(region3)
                plt.plot((offset+np.arange(len(region4)))*hp.delta_t, region4)
                plt.grid()
                plt.savefig('DEBUG-TaperingWindow.png')
            #
            win = np.concatenate((region1,region2,region3,region4,region5))
        elif 'cos' in tapermethod:
            win = region1
            win12 = 0.5 + 0.5*np.array([np.cos( np.pi*(float(j-ntaper1)/float(ntaper2-\
                                  ntaper1) - 1)) for j in np.arange(ntaper1,ntaper2)])
            win = np.append(win, win12)
            win = np.append(win, region3)
            win34 = 0.5 - 0.5*np.array([np.cos( np.pi*(float(j-ntaper3)/float(ntaper4-\
                                  ntaper3) - 1)) for j in np.arange(ntaper3,ntaper4)])
            win = np.append(win, win34)
            win = np.append(win, region5)
        else: raise IOError("Please specify valid taper-method")
        ##########################################################
        # ##########   Taper & Filter the waveform   #############
        ##########################################################
        hp.data *= win
        hc.data *= win
        #
        # High pass filter the waveform
        if f_filter > 0:
            hplal = convert_TimeSeries_to_lalREAL8TimeSeries( hp )
            hclal = convert_TimeSeries_to_lalREAL8TimeSeries( hc )
            lal.HighPassREAL8TimeSeries( hplal, f_filter, 0.9, 8 )
            lal.HighPassREAL8TimeSeries( hclal, f_filter, 0.9, 8 )
            hp = convert_lalREAL8TimeSeries_to_TimeSeries( hplal )
            hc = convert_lalREAL8TimeSeries_to_TimeSeries( hclal )

        return hp, hc
        #}}}
    #}}}

## Alias "nr_strain" to "nr_wave".
nr_wave = nr_strain
