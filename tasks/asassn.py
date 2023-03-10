"""Tasks related to the ASASSN survey."""
import json
import os
import re
from decimal import Decimal

from astrocats.structures.struct import PHOTOMETRY
from astrocats.utils import jd_to_mjd, pbar
from astropy.io.ascii import read
from bs4 import BeautifulSoup

from ..supernova import SUPERNOVA


def do_asassn(catalog):
    """Import list of ASASSN events."""
    task_str = catalog.get_current_task_str()
    asn_url = 'http://www.astronomy.ohio-state.edu/~assassin/sn_list.html'
    html = catalog.load_url(asn_url, os.path.join(
        catalog.get_current_task_repo(), 'ASASSN/sn_list.html'))
    if not html:
        return
    bs = BeautifulSoup(html, 'html5lib')
    trs = bs.find('table').findAll('tr')
    for tri, tr in enumerate(pbar(trs, task_str)):
        name = None
        ra = None
        dec = None
        redshift = None
        hostoff = None
        claimedtype = None
        host = None
        atellink = None
        typelink = None
        if tri == 0:
            continue
        tds = tr.findAll('td')
        if not len(tds):
            continue
        for tdi, td in enumerate(tds):
            if tdi == 1:
                name = catalog.add_entry(td.text.strip())
                atellink = td.find('a')
                if atellink:
                    atellink = atellink['href']
                else:
                    atellink = None
            if tdi == 2:
                discdate = td.text.replace('-', '/')
            if tdi == 3:
                ra = td.text
            if tdi == 4:
                dec = td.text
            if tdi == 5:
                redshift = td.text
            if tdi == 8:
                hostoff = td.text
            if tdi == 9:
                claimedtype = td.text
                typelink = td.find('a')
                if typelink:
                    typelink = typelink['href']
                else:
                    typelink = None
            if tdi == 12:
                host = td.text

        sources = [catalog.entries[name].add_source(url=asn_url, name='ASAS-SN Supernovae')]
        typesources = sources[:]
        if atellink is not None:
            src_name = 'ATel ' + atellink.split('=')[-1]
            src = catalog.entries[name].add_source(name=src_name, url=atellink)
            sources.append(src)
        if typelink is not None:
            src_name = 'ATel ' + typelink.split('=')[-1]
            src = catalog.entries[name].add_source(name=src_name, url=typelink)
            typesources.append(src)

        sources = ','.join(sources)
        typesources = ','.join(typesources)
        catalog.entries[name].add_quantity(SUPERNOVA.ALIAS, name, sources)
        catalog.entries[name].add_quantity(SUPERNOVA.DISCOVER_DATE, discdate, sources)
        if ra is not None:
            catalog.entries[name].add_quantity(SUPERNOVA.RA, ra, sources, u_value='floatdegrees')
        if dec is not None:
            catalog.entries[name].add_quantity(SUPERNOVA.DEC, dec, sources, u_value='floatdegrees')
        if redshift is not None:
            catalog.entries[name].add_quantity(SUPERNOVA.REDSHIFT, redshift, sources)
        if hostoff is not None:
            catalog.entries[name].add_quantity(
                SUPERNOVA.HOST_OFFSET_ANG, hostoff, sources, u_value='arcseconds')
        if claimedtype is not None:
            for ct in claimedtype.split('/'):
                if ct != 'Unk':
                    catalog.entries[name].add_quantity(SUPERNOVA.CLAIMED_TYPE, ct, typesources)
        if host != 'Uncatalogued':
            catalog.entries[name].add_quantity(SUPERNOVA.HOST, host, sources)

    catalog.journal_entries()
    return


def do_asas_atels(catalog):
    """Import LCs exposed in ASASSN Atels."""
    import gzip

    try:
        with gzip.open('/root/better-atel/atels.json.gz', 'rb') as f:
            ateljson = json.load(f)
    except Exception:
        print('ATel data unavailable, skipping ASAS ATel task.')
        return

    for entry in ateljson:
        if ('asas-sn.osu.edu/light_curve' in entry['body'] and
                'Supernovae' in entry['subjects']):
            matches = re.findall(r'<a\s+[^>]*?href="([^"]*)".*?>(.*?)<\/a>',
                                 entry['body'], re.DOTALL)
            lcurl = ''
            objname = ''
            for match in matches:
                if 'asas-sn.osu.edu/light_curve' in match[0]:
                    lcurl = match[0]
                    objname = re.findall(r'\bASASSN-[0-9][0-9].*?\b', match[1])
                    if len(objname):
                        objname = objname[0]
            if objname and lcurl:
                name, source = catalog.new_entry(
                    objname, name='ASAS-SN Sky Patrol',
                    bibcode='2017arXiv170607060K', url='https://asas-sn.osu.edu')
                csv = catalog.load_url(lcurl + '.csv', os.path.join(
                    catalog.get_current_task_repo(), os.path.join(
                        'ASASSN', objname + '.csv')))
                data = read(csv, format='csv')
                for row in data:
                    mag = str(row['mag'])
                    if float(mag.strip('>')) > 50.0:
                        continue
                    photodict = {
                        PHOTOMETRY.TIME: str(jd_to_mjd(Decimal(str(row['HJD'])))),
                        PHOTOMETRY.MAGNITUDE: mag.strip('>'),
                        PHOTOMETRY.SURVEY: 'ASASSN',
                        PHOTOMETRY.SOURCE: source
                    }
                    if '>' in mag:
                        photodict[PHOTOMETRY.UPPER_LIMIT] = True
                    else:
                        photodict[PHOTOMETRY.E_MAGNITUDE] = str(row['mag_err'])
                    catalog.entries[name].add_photometry(**photodict)
    catalog.journal_entries()
    return
