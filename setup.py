#!/usr/bin/env python

# Copyright (c) 2018, Prayush Kumar
# See LICENSE file for details: <https://github.com/prayush/GWNRTools/blob/master/LICENSE>

# Construct the version number from the date and time this python version was created.
from os import environ
if "package_version" in environ:
    version = environ["package_version"]
    print("Setup.py using environment version='{0}'".format(version))
else:
    print("The variable 'package_version' was not present in the environment")
    try:
        from subprocess import check_output
        version = check_output("""git log -1 --format=%cd --date=format:'%Y.%m.%d.%H.%M.%S'""", shell=use_shell).decode('ascii').rstrip()
        print("Setup.py using git log version='{0}'".format(version))
    except:
        from time import strftime, gmtime
        version = strftime("%Y.%m.%d.%H.%M.%S", gmtime())
        print("Setup.py using strftime version='{0}'".format(version))
with open('_version.py', 'w') as f:
    f.write('__version__ = "{0}"'.format(version))


if __name__ == "__main__":
    from distutils.core import setup
    setup(name='GWNRTools',
          version=version,
          description='Manipulating GW data in the form of time-dependent functions of spin-weighted spherical harmonics from NR simulations',
          url='https://github.com/prayush/GWNRTools',
          author='Prayush Kumar',
          author_email='prayush.kumar@gmail.com',
          package_dir={'GWNRTools': 'GWNRTools'},
          packages=['GWNRTools','GWNRTools.Cosmo','GWNRTools.DataAnalysis','GWNRTools.NR','GWNRTools.Plotting','GWNRTools.Stats','GWNRTools.Utils','GWNRTools.Waveforms'],
          requires=['numpy', 'scipy', 'pycbc', 'lal'],
    )
