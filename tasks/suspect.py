"""Import tasks for SUSPECT.
"""
import csv
import json
import os
import re
import urllib
from glob import glob
from html import unescape
from math import floor

# from astropy.time import Time as astrotime
from bs4 import BeautifulSoup

from astrocats.structures.struct import PHOTOMETRY, SPECTRUM
from astrocats.utils import (astrotime, get_sig_digits, is_number, jd_to_mjd,
                             pbar, pretty_num, uniq_cdl)
from decimal import Decimal

from ..supernova import SUPERNOVA


def do_suspect_photo(catalog):
    task_str = catalog.get_current_task_str()
    path = os.path.join(catalog.get_current_task_repo(), 'suspectreferences.csv')
    with open(path, 'r') as f:
        tsvin = csv.reader(f, delimiter=',', skipinitialspace=True)
        suspectrefdict = {}
        for row in tsvin:
            suspectrefdict[row[0]] = row[1]

    pattern = os.path.join(catalog.get_current_task_repo(), 'SUSPECT/*.html')
    file_names = list(sorted(glob(pattern)))
    for datafile in pbar(file_names, task_str, sort=True):
        basename = os.path.basename(datafile)
        basesplit = basename.split('-')
        oldname = basesplit[1]
        name = catalog.add_entry(oldname)
        if name.startswith('SN') and is_number(name[2:]):
            name = name + 'A'
        band = basesplit[3].split('.')[0]
        ei = int(basesplit[2])
        bandlink = 'file://' + os.path.abspath(datafile)
        bandresp = urllib.request.urlopen(bandlink)
        bandsoup = BeautifulSoup(bandresp, 'html5lib')
        bandtable = bandsoup.find('table')

        names = bandsoup.body.findAll(text=re.compile('Name'))
        reference = ''
        for link in bandsoup.body.findAll('a'):
            if 'adsabs' in link['href']:
                reference = str(link).replace('"', "'")

        bibcode = unescape(suspectrefdict[reference])
        source = catalog.entries[name].add_source(bibcode=bibcode)

        sec_ref = 'SUSPECT'
        sec_refurl = 'https://www.nhn.ou.edu/~suspect/'
        sec_source = catalog.entries[name].add_source(name=sec_ref, url=sec_refurl, secondary=True)
        catalog.entries[name].add_quantity(SUPERNOVA.ALIAS, oldname, sec_source)

        if ei == 1:
            year = re.findall(r'\d+', name)[0]
            catalog.entries[name].add_quantity(SUPERNOVA.DISCOVER_DATE, year, sec_source)
            catalog.entries[name].add_quantity(
                SUPERNOVA.HOST, names[1].split(':')[1].strip(), sec_source)

            redshifts = bandsoup.body.findAll(text=re.compile('Redshift'))
            if redshifts:
                catalog.entries[name].add_quantity(
                    SUPERNOVA.REDSHIFT, redshifts[0].split(':')[1].strip(),
                    sec_source, kind='heliocentric')
            # hvels = bandsoup.body.findAll(text=re.compile('Heliocentric
            # Velocity'))
            # if hvels:
            #     vel = hvels[0].split(':')[1].strip().split(' ')[0]
            #     catalog.entries[name].add_quantity(SUPERNOVA.VELOCITY, vel,
            # sec_source,
            # kind='heliocentric')
            types = bandsoup.body.findAll(text=re.compile('Type'))

            catalog.entries[name].add_quantity(
                SUPERNOVA.CLAIMED_TYPE, types[0].split(':')[1].strip().split(' ')[0], sec_source)

        for r, row in enumerate(bandtable.findAll('tr')):
            if r == 0:
                continue
            col = row.findAll('td')
            mjd = str(jd_to_mjd(Decimal(col[0].contents[0])))
            mag = col[3].contents[0]
            if mag.isspace():
                mag = ''
            else:
                mag = str(mag)
            e_magnitude = col[4].contents[0]
            photo = {
                PHOTOMETRY.TIME: mjd,
                PHOTOMETRY.U_TIME: 'MJD',
                PHOTOMETRY.BAND: band,
                PHOTOMETRY.MAGNITUDE: mag,
                PHOTOMETRY.SOURCE: sec_source + ',' + source
            }
            if not e_magnitude.isspace():
                photo[PHOTOMETRY.E_MAGNITUDE] = str(e_magnitude)
            catalog.entries[name].add_photometry(**photo)

    catalog.journal_entries()
    return


def do_suspect_spectra(catalog):
    task_str = catalog.get_current_task_str()
    path = os.path.join(catalog.get_current_task_repo(), 'Suspect/sources.json')
    with open(path, 'r') as f:
        sourcedict = json.loads(f.read())

    path = os.path.join(catalog.get_current_task_repo(), 'Suspect/filename-changes.txt')
    with open(path, 'r') as f:
        rows = f.readlines()
        changedict = {}
        for row in rows:
            if not row.strip() or row[0] == "#":
                continue
            items = row.strip().split(' ')
            changedict[items[1]] = items[0]

    suspectcnt = 0
    folders = next(os.walk(os.path.join(catalog.get_current_task_repo(), 'Suspect')))[1]
    for folder in pbar(folders, task_str):
        path = os.path.join(catalog.get_current_task_repo(), 'Suspect/') + folder
        eventfolders = next(os.walk(path))[1]
        oldname = ''
        for eventfolder in pbar(eventfolders, task_str):
            name = eventfolder
            if is_number(name[:4]):
                name = 'SN' + name
            # If entry already exists use name
            _name = catalog.get_name_for_entry_or_alias(name)
            if _name is not None:
                name = _name
            if oldname and name != oldname:
                catalog.journal_entries()
            oldname = name
            name = catalog.add_entry(name)
            sec_ref = 'SUSPECT'
            sec_refurl = 'https://www.nhn.ou.edu/~suspect/'
            sec_bibc = '2001AAS...199.8408R'
            sec_source = catalog.entries[name].add_source(
                name=sec_ref, url=sec_refurl, bibcode=sec_bibc, secondary=True)
            catalog.entries[name].add_quantity(SUPERNOVA.ALIAS, name, sec_source)
            fpath = os.path.join(catalog.get_current_task_repo(), 'Suspect', folder, eventfolder)
            eventspectra = next(os.walk(fpath))[2]
            for spectrum in eventspectra:
                sources = [sec_source]
                bibcode = ''
                if spectrum in changedict:
                    specalias = changedict[spectrum]
                else:
                    specalias = spectrum
                if specalias in sourcedict:
                    bibcode = sourcedict[specalias]
                elif name in sourcedict:
                    bibcode = sourcedict[name]
                if bibcode:
                    source = catalog.entries[name].add_source(bibcode=unescape(bibcode))
                    sources += [source]
                sources = uniq_cdl(sources)

                date = spectrum.split('_')[1]
                year = date[:4]
                month = date[4:6]
                day = date[6:]
                sig = get_sig_digits(day) + 5
                day_fmt = str(floor(float(day))).zfill(2)
                # time = astrotime(year + '-' + month + '-' + day_fmt).mjd
                time = astrotime(year + '-' + month + '-' + day_fmt, input=None, output='mjd')
                time = time + float(day) - floor(float(day))
                time = pretty_num(time, sig=sig)

                fpath = os.path.join(
                    catalog.get_current_task_repo(), 'Suspect', folder, eventfolder, spectrum)
                with open(fpath, 'r') as f:
                    specdata = list(csv.reader(f, delimiter=' ', skipinitialspace=True))
                    specdata = list(filter(None, specdata))
                    newspec = []
                    oldval = ''
                    for row in specdata:
                        if row[1] == oldval:
                            continue
                        newspec.append(row)
                        oldval = row[1]
                    specdata = newspec
                haserrors = len(specdata[0]) == 3 and specdata[0][2] and specdata[0][2] != 'NaN'
                specdata = [list(i) for i in zip(*specdata)]

                wavelengths = specdata[0]
                fluxes = specdata[1]

                spec = {
                    SPECTRUM.U_WAVELENGTHS: 'Angstrom',
                    SPECTRUM.U_FLUXES: 'Uncalibrated',
                    SPECTRUM.U_TIME: 'MJD',
                    SPECTRUM.TIME: time,
                    SPECTRUM.WAVELENGTHS: wavelengths,
                    SPECTRUM.FLUXES: fluxes,
                    SPECTRUM.U_ERRORS: 'Uncalibrated',
                    SPECTRUM.SOURCE: sources,
                    SPECTRUM.FILENAME: spectrum
                }
                if haserrors:
                    spec[SPECTRUM.ERRORS] = specdata[2]

                catalog.entries[name].add_spectrum(**spec)

                suspectcnt = suspectcnt + 1
                if catalog.args.travis and (suspectcnt > catalog.TRAVIS_QUERY_LIMIT):
                    break

    catalog.journal_entries()
    return
