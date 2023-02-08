# -*- coding: utf-8 -*-
import re
import datetime
import time
import json
import os
import urllib.parse
from models import Rating
import config
from tests.sitespeed_base import get_result
from bs4 import BeautifulSoup
import gettext

from tests.utils import httpRequestGetContent
_ = gettext.gettext

review_show_improvements_only = config.review_show_improvements_only
sitespeed_use_docker = config.sitespeed_use_docker
checked_urls = {}
digg_url = 'https://www.digg.se/tdosanmalan'
canonical = 'https://www.digg.se/tdosanmalan'


def run_test(_, langCode, url):
    """

    """

    language = gettext.translation(
        'a11y_pa11y', localedir='locales', languages=[langCode])
    language.install()
    _local = language.gettext

    print(_local('TEXT_RUNNING_TEST'))

    print(_('TEXT_TEST_START').format(
        datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    return_dict = {}
    rating = Rating(_, review_show_improvements_only)

    o = urllib.parse.urlparse(url)
    org_url_start = '{0}://{1}'.format(o.scheme,
                                       o.hostname)
    global canonical
    canonical = get_digg_report_canonical()

    start_item = get_default_info(url, '', 'url.start', 0.0, 0)
    statements = check_item(start_item, None, org_url_start, _)

    if statements != None:
        for statement in statements:
            for item in start_item['items']:
                if statement['url'] == item['url'] and statement['depth'] > item['depth']:
                    statement['depth'] = item['depth']

            rating += rate_statement(statement, _)
            # Should we test all found urls or just best match?
            break
    else:
        rating += rate_statement(None, _)

    print(_('TEXT_TEST_END').format(
        datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    return (rating, return_dict)


def get_digg_report_canonical():
    content = httpRequestGetContent(digg_url)
    content_match = re.search(
        r'<link rel="canonical" href="(?P<url>[^"]+)', content)
    if content_match:
        o = urllib.parse.urlparse(digg_url)
        org_url_start = '{0}://{1}'.format(o.scheme,
                                           o.hostname)
        url = content_match.group('url')
        if url.startswith('/'):
            url = '{0}{1}'.format(org_url_start, url)
    return url


def check_item(item, root_item, org_url_start, _):
    statements = list()
    content = None
    if item['url'] not in checked_urls:
        content = httpRequestGetContent(item['url'], True)
        time.sleep(1)
        checked_urls[item['url']] = content
    else:
        content = checked_urls[item['url']]
        # return statements

    item['root'] = root_item
    if root_item == None:
        item['items'] = list()
    else:
        item['items'] = item['root']['items']

    item['validated'] = True
    item['children'] = get_interesting_urls(
        content, org_url_start, item['depth'] + 1)

    item['content'] = content
    if has_statement(item, _):
        item['precision'] = 1.0
        statements.append(item)
    elif item['depth'] < 2:
        del item['content']
        child_index = 0
        for child_pair in item['children'].items():
            if child_index > 10:
                break
            child_index += 1
            child = child_pair[1]
            item['items'].append(child)
            if len(statements) > 0 and child['precision'] < 0.5:
                continue
            tmp = check_item(child, root_item, org_url_start, _)
            if tmp != None:
                statements.extend(tmp)

    if len(statements) > 0:
        return statements
    return None


def has_statement(item, _):
    rating = rate_statement(item, _)
    if rating.get_overall() > 1:
        return True

    return False


def get_default_info(url, text, method, precision, depth):
    result = {}

    if text != None:
        text = text.lower().strip('.').strip('-').strip()

    result['url'] = url
    result['method'] = method
    result['precision'] = precision
    result['text'] = text
    result['depth'] = depth

    return result


def rate_statement(statement, _):
    # https://www.digg.se/kunskap-och-stod/digital-tillganglighet/skapa-en-tillganglighetsredogorelse
    rating = Rating(_, review_show_improvements_only)

    if statement != None:
        # rating.set_overall(
        #     5.0, '- Tillgänglighetsredogörelse: {0}'.format(statement['url']))
        # rating.set_overall(
        #     5.0, '- Tillgänglighetsredogörelse hittad')
        statement_content = statement['content']
        soup = BeautifulSoup(statement_content, 'lxml')

        # STATEMENTS MUST INCLUDE (ACCORDING TO https://www.digg.se/kunskap-och-stod/digital-tillganglighet/skapa-en-tillganglighetsredogorelse ):
        # - Namnet på den offentliga aktören.
        # - Namnet på den digitala servicen (till exempel webbplatsens, e-tjänstens eller appens namn).
        # - Följsamhet till lagkraven med formuleringen: helt förenlig, delvis förenlig eller inte förenlig.
        rating += rate_compatible_text(_, soup)
        # - Detaljerad, fullständig och tydlig förteckning av innehåll som inte är tillgängligt och skälen till varför det inte är tillgängligt.
        # - Datum för bedömning av följsamhet till lagkraven.
        # - Datum för senaste uppdatering.
        # - Meddelandefunktion eller länk till sådan.
        # - Länk till DIGG:s anmälningsfunktion (https://www.digg.se/tdosanmalan).
        rating += rate_notification_function_url(_, soup)
        # - Redogörelse av innehåll som undantagits på grund av oskäligt betungande anpassning (12 §) med tydlig motivering.
        rating += rate_unreasonably_burdensome_accommodation(_, soup)
        # - Redogörelse av innehåll som inte omfattas av lagkraven (9 §).

        # - Redogörelsen ska vara lätt att hitta
        #   - Tillgänglighetsredogörelsen ska vara publicerad i ett tillgängligt format (det bör vara en webbsida).
        #   - För en webbplats ska en länk till tillgänglighetsredogörelsen finnas tydligt presenterad på webbplatsens startsida, alternativt finnas åtkomlig från alla sidor exempelvis i en sidfot.

        if rating.get_overall() > 1 or looks_like_statement(statement, soup):
            rating += rate_found_depth(_, statement)
            # - Utvärderingsmetod (till exempel självskattning, granskning av extern part).
            rating += rate_evaluation_method(_, soup)

        rating.overall_review = '- Tillgänglighetsredogörelse: {0}\r\n{1}'.format(
            statement['url'], rating.overall_review)
    else:
        rating.set_overall(1.0, '- Ingen tillgänglighetsredogörelse hittad')

    return rating


def looks_like_statement(statement, soup):
    element = soup.find('h1', string=re.compile(
        "tillg(.{1,6}|ä|&auml;|&#228;)nglighetsredog(.{1,6}|ö|&ouml;|&#246;)relse", flags=re.MULTILINE | re.IGNORECASE))
    if element:
        return True

    element = soup.find('title', string=re.compile(
        "tillg(.{1,6}|ä|&auml;|&#228;)nglighetsredog(.{1,6}|ö|&ouml;|&#246;)relse", flags=re.MULTILINE | re.IGNORECASE))
    if element:
        return True

    if statement['precision'] >= 0.5:
        return True

    return False


def rate_found_depth(_, statement):
    rating = Rating(_, review_show_improvements_only)

    depth = statement["depth"]

    if depth == 1:
        rating.set_overall(
            5.0, '- Länk till tillgänglighetsredogörelsen finnas tydligt presenterad på webbplatsens startsida')
    elif depth > 1:
        rating.set_overall(
            3.0, '- Tillgänglighetsredogörelsen hittades på ett länkdjup större än den bör')

    return rating


def rate_evaluation_method(_, soup):
    match = soup.find(string=re.compile(
        "(sj(.{1, 6} | ä | &auml; | &  # 228;)lvskattning|interna kontroller|intern testning|utvärderingsmetod|tillgänglighetsexperter|funka|etu ab|siteimprove|oberoende granskning|oberoende tillgänglighetsgranskningar|tillgänglighetskonsult|med hjälp av|egna tester|oberoende experter|Hur vi testat webbplatsen|vi testat webbplatsen|intervjuer|rutiner|checklistor|checklista|utbildningar)", flags=re.MULTILINE | re.IGNORECASE))
    rating = Rating(_, review_show_improvements_only)
    if match:
        rating.set_overall(
            5.0, '- Ser ut att ange utvärderingsmetod')
    else:
        rating.set_overall(
            1.0, '- Hittar ej info om utvärderingsmetod')

    return rating


def rate_unreasonably_burdensome_accommodation(_, soup):
    match = soup.find(string=re.compile(
        "(Oskäligt betungande anpassning|12[ \t\r\n]§ lagen)", flags=re.MULTILINE | re.IGNORECASE))
    rating = Rating(_, review_show_improvements_only)
    if match:
        rating.set_overall(
            5.0, '- Anger oskäligt betungande anpassning (12 §)')
        rating.set_a11y(
            4.0, '- Anger oskäligt betungande anpassning (12 §)')
    else:
        # rating.set_overall(
        #     5.0, '- Anger ej oskäligt betungande anpassning (12 §)')
        rating.set_a11y(
            5.0, '- Anger ej oskäligt betungande anpassning (12 §)')

    return rating


def rate_notification_function_url(_, soup):
    match_correct_url = soup.find(href=digg_url)

    match_canonical_url = soup.find(href=canonical)

    match_old_reference = soup.find(href=re.compile(
        "digg\.se[a-z\/\-]+anmal-bristande-tillganglighet", flags=re.MULTILINE | re.IGNORECASE))

    is_digg = False
    for i in soup.select('link[rel*=canonical]'):
        if 'digg.se' in i['href']:
            is_digg = True
    if is_digg:
        # NOTE: digg.se has of course all links relative. This is a fix for that..
        match_canonical_url = soup.find(
            href=canonical.replace('https://www.digg.se', ''))

    rating = Rating(_, review_show_improvements_only)
    if match_correct_url:
        rating.set_overall(
            5.0, '- Korrekt länk till DIGG:s anmälningsfunktion')
    elif match_canonical_url:
        rating.set_overall(
            5.0, '- Korrekt länk ("canonical") till DIGG:s anmälningsfunktion')
    elif match_old_reference:
        rating.set_overall(
            4.5, '- Använder gammal eller felaktig länk till DIGG:s anmälningsfunktion')
    else:
        rating.set_overall(
            1.0, '- Saknar eller har felaktig länk till DIGG:s anmälningsfunktion')

    return rating


def rate_compatible_text(_, soup):
    element = soup.find(string=re.compile(
        "(?P<test>helt|delvis|inte) förenlig", flags=re.MULTILINE | re.IGNORECASE))
    rating = Rating(_, review_show_improvements_only)
    if element:
        text = element.get_text()
        regex = r'(?P<test>helt|delvis|inte) förenlig'
        match = re.search(regex, text, flags=re.IGNORECASE)
        test = match.group('test').lower()
        if 'inte' in test:
            rating.set_overall(
                5.0, '- Har följsamhet till lagkraven med formuleringen "inte förenlig"')
            rating.set_a11y(
                1.0, '- Anger själv att webbplats "inte" är förenlig med lagkraven')
        elif 'delvis' in test:
            rating.set_overall(
                5.0, '- Har följsamhet till lagkraven med formuleringen "delvis förenlig"')
            rating.set_a11y(
                3.0, '- Anger själv att webbplats bara "delvis" är förenlig med lagkraven')
        else:
            rating.set_overall(
                5.0, '- Har följsamhet till lagkraven med formuleringen "helt förenlig"')
            rating.set_a11y(
                5.0, '- Anger själv att webbplats är "helt" förenlig med lagkraven')
    else:
        rating.set_overall(
            1.0, '- Saknar följsamhet till lagkraven med formuleringen')

    return rating


def get_sort_on_precision(item):
    return item[1]["precision"]


def get_interesting_urls(content, org_url_start, depth):
    urls = {}

    soup = BeautifulSoup(content, 'lxml')
    links = soup.find_all("a")

    for link in links:
        if not link.find(string=re.compile(
                r"(om [a-z]+|(tillg(.{1,6}|ä|&auml;|&#228;)nglighet(sredog(.{1,6}|ö|&ouml;|&#246;)relse){0,1}))", flags=re.MULTILINE | re.IGNORECASE)):
            continue

        url = '{0}'.format(link.get('href'))

        if url == None:
            continue
        elif url.endswith('.pdf'):
            continue
        elif url.startswith('//'):
            continue
        elif url.startswith('/'):
            url = '{0}{1}'.format(org_url_start, url)
        elif url.startswith('#'):
            continue

        if not url.startswith(org_url_start):
            continue

        text = link.get_text().strip()

        precision = 0.0
        if re.match(r'^[ \t\r\n]*tillg(.{1,6}|ä|&auml;|&#228;)nglighetsredog(.{1,6}|ö|&ouml;|&#246;)relse$', text, flags=re.MULTILINE | re.IGNORECASE) != None:
            precision = 0.55
        elif re.match(r'^[ \t\r\n]*tillg(.{1,6}|ä|&auml;|&#228;)nglighetsredog(.{1,6}|ö|&ouml;|&#246;)relse', text, flags=re.MULTILINE | re.IGNORECASE) != None:
            precision = 0.5
        elif re.match(r'^[ \t\r\n]*tillg(.{1,6}|ä|&auml;|&#228;)nglighet$', text, flags=re.MULTILINE | re.IGNORECASE) != None:
            precision = 0.4
        elif re.match(r'^[ \t\r\n]*tillg(.{1,6}|ä|&auml;|&#228;)nglighet', text, flags=re.MULTILINE | re.IGNORECASE) != None:
            precision = 0.35
        elif re.match(r'tillg(.{1,6}|ä|&auml;|&#228;)nglighet', text, flags=re.MULTILINE | re.IGNORECASE) != None:
            precision = 0.3
        elif re.search(r'om webbplats', text, flags=re.MULTILINE | re.IGNORECASE) != None:
            precision = 0.29
        elif re.match(r'^[ \t\r\n]*om [a-z]+$', text, flags=re.MULTILINE | re.IGNORECASE) != None:
            precision = 0.25
        elif re.match(r'^[ \t\r\n]*om [a-z]+', text, flags=re.MULTILINE | re.IGNORECASE) != None:
            precision = 0.2
        else:
            precision = 0.1

        info = get_default_info(
            url, text, 'url.text', precision, depth)
        if url not in checked_urls:
            urls[url] = info

    if len(urls) > 0:
        urls = dict(
            sorted(urls.items(), key=get_sort_on_precision, reverse=True))
        return urls
    return urls


"""
If file is executed on itself then call a definition, mostly for testing purposes
"""
if __name__ == '__main__':
    print(run_test('sv', 'https://webperf.se'))
