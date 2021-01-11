# -*- coding: utf-8 -*-

from __future__ import unicode_literals
from kodi_six.utils import py2_encode, py2_decode

import _strptime

import base64
import calendar
from datetime import datetime, timedelta
from hashlib import sha1, sha256
from inputstreamhelper import Helper
import json
import os
import re
import requests
import sys
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

try:
    import urllib.parse as urllib
except ImportError:
    import urllib

addon_handle = int(sys.argv[1])
addon = xbmcaddon.Addon()
addonPath = py2_decode(xbmc.translatePath(addon.getAddonInfo('path')))
defaultFanart = os.path.join(addonPath, 'resources/fanart.png')
icon = os.path.join(addonPath, 'resources/icon.png')
baseURL = "https://www."
pluginBaseUrl = "plugin://{0}".format(addon.getAddonInfo('id'))
userAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'
bv = xbmc.getInfoLabel('System.BuildVersion')
kodiVersion = int(bv.split('.')[0])
dayNames = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']


def listShows(entry):
    content = getContentFull(entry.get('domain'), entry.get('path'))
    if content and len(content) > 0:
        shows = getListItems(content.get('data', None), 'show').get('items')
        for show in shows:
            infoLabels = show.get('infoLabels', {})
            art = show.get('art')
            domain = entry.get('domain')
            if show.get('contentType') == 'redirect':
                match = re.search('http?:\/\/[w]{0,3}\.?([^\/]*)', show.get('url'))
                if match:
                    domain = match.group(1)
                    show.update({'url': ''})
            url = build_url({'action': 'showcontent', 'entry': {'domain': domain, 'path': '{0}{1}'.format(show.get('url'), '/video'), 'cmsId': show.get('cmsId'), 'type': 'season', 'art': art, 'infoLabels': infoLabels}})
            addDir(label=infoLabels.get('title'), url=url, art=art, infoLabels=infoLabels)

    xbmcplugin.setContent(addon_handle, 'tvshows')
    xbmcplugin.addSortMethod(addon_handle, sortMethod=xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(addon_handle, cacheToDisc=True)


def listShowcontent(entry):
    content = getContentFull(entry.get('domain'), entry.get('path'))
    if content and len(content) > 0:
        detail = getListItems(content.get('data', None), entry.get('type'), entry.get('domain'), entry.get('path'), entry.get('cmsId'))
        items = detail.get('items')

        seasons = sorted(list(dict.fromkeys(['{0}'.format(item.get('infoLabels', {}).get('season')) for item in items if item.get('infoLabels', {}).get('season')])))
        if detail.get('type') == 'episode' and entry.get('type') == 'season' and len(seasons) > 1:
            for season in seasons:
                url = build_url({'action': 'showcontent', 'entry': {'domain': entry.get('domain'), 'path': entry.get('path'), 'cmsId': entry.get('cmsId'), 'seasonno': season, 'type': 'episode'}})
                addDir(label='Staffel {0}'.format(season), url=url, art=entry.get('art'), infoLabels=entry.get('infoLabels'))

            noseasons = [item for item in items if not item.get('infoLabels', {}).get('season')]
            if len(noseasons) > 0:
                url = build_url({'action': 'showcontent', 'entry': {'domain': entry.get('domain'), 'path': entry.get('path'), 'cmsId': entry.get('cmsId'), 'seasonno': None, 'type': 'episode'}})
                addDir(label='Videos ohne Staffelzuordnung', url=url, art=entry.get('art'), infoLabels=entry.get('infoLabels'))

            xbmcplugin.setContent(addon_handle, 'tvshows')
        else:
            addon_content = None
            addon_sortmethods = []
            for item in items:
                infoLabels = item.get('infoLabels', {})
                if detail.get('type') == 'season':
                    addon_content = 'tvshows'
                    addon_sortmethods.append(xbmcplugin.SORT_METHOD_LABEL)
                    entry_infoLabels = entry.get('infoLabels', {})
                    infoLabels.update({'plot': entry_infoLabels.get('plot')})
                    cmsId = detail.get('cmsId') if detail.get('cmsId') else entry.get('cmsId')

                    url = build_url({'action': 'showcontent', 'entry': {'domain': entry.get('domain'), 'path': item.get('url'), 'cmsId': cmsId, 'seasonno': infoLabels.get('season')}})
                    addDir(label='Staffel {0}'.format(infoLabels.get('season')), url=url, art=entry.get('art'), infoLabels=infoLabels)
                else:
                    if detail.get('type') != 'episode' and entry.get('seasonno') and infoLabels.get('season') != int(entry.get('seasonno')):
                        continue
                    elif detail.get('type') != 'episode' and not entry.get('seasonno') and infoLabels.get('season'):
                        continue
                    elif entry.get('type') == 'episode' and entry.get('seasonno') and infoLabels.get('season') != int(entry.get('seasonno')):
                        continue
                    elif entry.get('type') == 'episode' and not entry.get('seasonno') and infoLabels.get('season'):
                        continue
                    addon_content = 'episodes'
                    if infoLabels.get('season') and infoLabels.get('episode'):
                        addon_sortmethods.extend([xbmcplugin.SORT_METHOD_EPISODE, xbmcplugin.SORT_METHOD_LABEL])
                    url = build_url({'action': 'play', 'entry': {'domain': entry.get('domain'), 'path': item.get('url')}})
                    addFile(infoLabels.get('title'), url, art=item.get('art', {}), infoLabels=infoLabels)

            if addon_content:
                xbmcplugin.setContent(addon_handle, addon_content)
            for sortmethod in addon_sortmethods:
                xbmcplugin.addSortMethod(addon_handle, sortMethod=sortmethod)

    xbmcplugin.endOfDirectory(addon_handle, cacheToDisc=True)


def listVideostruct(entry):
    content = getContentFull(entry.get('domain'), entry.get('path'))
    if content and content.get('data', None):
        structs = dict(folder=list(), videos=list())
        if content.get('data').get('site', None) and content.get('data').get('site').get('path', None) and content.get('data').get('site').get('path').get('content', None) and content.get('data').get('site').get('path').get('content').get('areas', None):
            areas = content.get('data').get('site').get('path').get('content').get('areas')
            if areas:
                for area in areas:
                    if area.get('id') == 'right':
                        continue
                    containers = area.get('containers')
                    for container in containers:
                        elements = container.get('elements', None)
                        if elements:
                            element = elements[0]
                            groups = element.get('groups', None)
                            if groups and groups[0].get('items'):
                                if element.get('title') and area.get('id') == 'bottom':
                                    structs.get('folder').append(element.get('title'))
                                else:
                                    for item in groups[0].get('items'):
                                        if item.get('contentType') == 'video':
                                            structs.get('videos').append(item)
                                    if groups[0].get('cursor'):
                                        structs.update(dict(pagination=dict(cursor=groups[0].get('cursor'), id=element.get('id'))))

        if structs.get('videos'):
            for item in structs.get('videos'):
                build_video(item, entry.get('domain'))

            if structs.get('pagination'):
                if len(structs.get('folder')) == 0:
                    build_pagination_dir(entry.get('domain'), structs.get('pagination').get('id'), structs.get('pagination').get('cursor'), 2)
                else:
                    cursor = structs.get('pagination').get('cursor')
                    while cursor:
                        content = getPagination(entry.get('domain'), structs.get('pagination').get('id'), cursor)
                        cursor = None
                        if content and content.get('data', None):    
                            if content.get('data').get('site', None) and content.get('data').get('site').get('items', None):
                                pagination_videos = content.get('data').get('site').get('items').get('items')
                                if pagination_videos:
                                    for video in pagination_videos:
                                        build_video(video, entry.get('domain'))
                                cursor = content.get('data').get('site').get('items').get('cursor')

        for folder in structs.get('folder'):
            art = dict()
            infoLabels = dict(plot=folder)

            url = build_url({'action': 'videos', 'entry': entry, 'folder': folder})
            addDir(label=folder, url=url, art=art, infoLabels=infoLabels)

    xbmcplugin.setContent(addon_handle, 'files')
    xbmcplugin.endOfDirectory(addon_handle, cacheToDisc=True)


def listVideos(entry, folder):
    content = getContentFull(entry.get('domain'), entry.get('path'))
    if content and content.get('data', None):
        videos = dict(items=list())
        if content.get('data').get('site', None) and content.get('data').get('site').get('path', None) and content.get('data').get('site').get('path').get('content', None) and content.get('data').get('site').get('path').get('content').get('areas', None):
            areas = content.get('data').get('site').get('path').get('content').get('areas')
            if areas:
                for area in areas:
                    containers = area.get('containers')
                    for container in containers:
                        elements = container.get('elements', None)
                        if elements:
                            element = elements[0]
                            groups = element.get('groups', None)
                            if groups and element.get('title') == folder:
                                videos.get('items').extend(groups[0].get('items'))
                                if groups[0].get('cursor'):
                                    videos.update(dict(pagination=dict(cursor=groups[0].get('cursor'), id=element.get('id'))))

        if videos.get('items'):
            for item in videos.get('items'):
                build_video(item, entry.get('domain'))

            if videos.get('pagination'):
                build_pagination_dir(entry.get('domain'), videos.get('pagination').get('id'), videos.get('pagination').get('cursor'), 2)

    xbmcplugin.setContent(addon_handle, 'files')
    xbmcplugin.endOfDirectory(addon_handle, cacheToDisc=True)


def listPaginationVideos(entry):
    content = getPagination(entry.get('domain'), entry.get('path'), entry.get('cursor'))
    if content and content.get('data', None):    
        if content.get('data').get('site', None) and content.get('data').get('site').get('items', None):
            videos = content.get('data').get('site').get('items').get('items')
            if videos:
                for video in videos:
                    build_video(video, entry.get('domain'))

                if content.get('data').get('site').get('items').get('cursor'):
                    build_pagination_dir(entry.get('domain'), entry.get('path'), content.get('data').get('site').get('items').get('cursor'), entry.get('page') + 1)

    xbmcplugin.setContent(addon_handle, 'files')
    xbmcplugin.endOfDirectory(addon_handle, cacheToDisc=True)


def getContentFull(domain, path):
    base = 'https://magellan-api.p7s1.io/content-full/{0}{1}/graphql'.format(domain, path)
    parameters = {'query': ' query FullContentQuery($domain: String!, $url: String!, $date: DateTime, $contentType: String, $debug: Boolean!, $authentication: AuthenticationInput) { site(domain: $domain, date: $date, authentication: $authentication) { domain path(url: $url) { content(type: FULL, contentType: $contentType) { ...fContent } somtag(contentType: $contentType) { ...fSomtag } tracking(contentType: $contentType) { ...fTracking } } } } fragment fContent on Content { areas { ...fContentArea } } fragment fContentArea on ContentArea { id containers { ...fContentContainer } filters { ...fFilterOptions } debug @include(if: $debug) { ...fContentDebugInfo } } fragment fContentContainer on ContentContainer { id style elements { ...fContentElement } } fragment fContentElement on ContentElement { id authentication title description component config style highlight navigation { ...fNavigationItem } regwall filters { ...fFilterOptions } update styleModifiers groups { id title total cursor itemSource { type id } items { ...fContentElementItem } debug @include(if: $debug) { ...fContentDebugInfo } } groupLayout debug @include(if: $debug) { ...fContentDebugInfo } } fragment fNavigationItem on NavigationItem { selected href channel { ...fChannelInfo } contentType title items { selected href channel { ...fChannelInfo } contentType title } } fragment fChannelInfo on ChannelInfo { title shortName cssId cmsId } fragment fFilterOptions on FilterOptions { type remote categories { name title options { title id channelId } } } fragment fContentElementItem on ContentElementItem { id url info branding { ...fBrand } body config headline contentType channel { ...fChannelInfo } site picture { url } videoType orientation date duration flags genres valid { from to } epg { episode { ...fEpisode } season { ...fSeason } duration nextEpgInfo { ...fEpgInfo } } debug @include(if: $debug) { ...fContentDebugInfo } } fragment fBrand on Brand { id, name } fragment fEpisode on Episode { number } fragment fSeason on Season { number } fragment fEpgInfo on EpgInfo { time endTime primetime } fragment fContentDebugInfo on ContentDebugInfo { source transformations { description } } fragment fSomtag on Somtag { configs } fragment fTracking on Tracking { context }'}
    parameters.update({'variables': '{{"authentication":null,"contentType":"frontpage","debug":false,"domain":"{0}","isMobile":false,"url":"{1}"}}'.format(domain, path)})
    url = '{0}?{1}'.format(base, urllib.urlencode(parameters).replace('+', '%20'))
    xbmc.log('url = {0}'.format(url))
    result = requests.get(url).json()
    if result and path.endswith('/video') and result.get('data', None) and result.get('data').get('site', None) and result.get('data').get('site').get('path', None) and not result.get('data').get('site').get('path').get('somtag'):
        result = getContentFull(domain, '{0}s'.format(path))
    return result


def getContentPreview(domain, path):
    base = 'https://magellan-api.p7s1.io/content-preview/{0}{1}/graphql'.format(domain, path)
    if path == '/livestream':
        parameters = {'query': 'query PreviewContentQuery($domain: String!, $url: String!, $date: DateTime, $contentType: String, $debug: Boolean!, $authentication: AuthenticationInput) { site(domain: $domain, date: $date, authentication: $authentication) { domain path(url: $url) { route { ...fRoute } page { ...fPage ...fLivestream24Page } content(type: PREVIEW, contentType: $contentType) { ...fContent } mainNav: navigation(type: MAIN) { items { ...fNavigationItem } } metaNav: navigation(type: META) { items { ...fNavigationItem } } channelNav: navigation(type: CHANNEL) { items { ...fNavigationItem } } showsNav: navigation(type: SHOWS) { items { ...fNavigationItem } } footerNav: navigation(type: FOOTER) { items { ...fNavigationItem } } networkNav: navigation(type: NETWORK) { items { ...fNavigationItem } } } } } fragment fRoute on Route { url exists authentication comment contentType name cmsId startDate status endDate } fragment fPage on Page { cmsId contentType pagination { ...fPagination } title shortTitle subheadline proMamsId additionalProMamsIds route source regWall { ...fRegWall } links { ...fLink } metadata { ...fMetadata } breadcrumbs { id href title text } channel { ...fChannel } seo { ...fSeo } modified published flags mainClassNames } fragment fPagination on Pagination { kind limit parent contentType } fragment fRegWall on RegWall { isActive start end } fragment fLink on Link { id classes language href relation title text outbound } fragment fMetadata on Metadata { property name content } fragment fChannel on Channel { name title shortName licenceTerms cssId cmsId proMamsId additionalProMamsIds route image hasLogo liftHeadings, logo sponsors { ...fSponsor } } fragment fSponsor on Sponsor { name url image } fragment fSeo on Seo { title keywords description canonical robots } fragment fLivestream24Page on Livestream24Page { ... on Livestream24Page { livestreamId contentResources epg { name items { ...fEpgItem tvShowTeaser { ...fTeaserItem } } } } } fragment fEpgItem on EpgItem { id title description startTime endTime episode { number } season { number } tvShow { title } images { url title copyright } links { href contentType title } } fragment fTeaserItem on TeaserItem { id url info headline contentType channel { ...fChannelInfo } branding { ...fBrand } site picture { url } videoType orientation date flags valid { from to } epg { episode { ...fEpisode } season { ...fSeason } duration nextEpgInfo { ...fEpgInfo } } } fragment fChannelInfo on ChannelInfo { title shortName cssId cmsId } fragment fBrand on Brand { id, name } fragment fEpisode on Episode { number } fragment fSeason on Season { number } fragment fEpgInfo on EpgInfo { time endTime primetime } fragment fContent on Content { areas { ...fContentArea } } fragment fContentArea on ContentArea { id containers { ...fContentContainer } filters { ...fFilterOptions } debug @include(if: $debug) { ...fContentDebugInfo } } fragment fContentContainer on ContentContainer { id style elements { ...fContentElement } } fragment fContentElement on ContentElement { id authentication title description component config style highlight navigation { ...fNavigationItem } regwall filters { ...fFilterOptions } update styleModifiers groups { id title total cursor itemSource { type id } items { ...fContentElementItem } debug @include(if: $debug) { ...fContentDebugInfo } } groupLayout debug @include(if: $debug) { ...fContentDebugInfo } } fragment fNavigationItem on NavigationItem { selected href channel { ...fChannelInfo } contentType title items { selected href channel { ...fChannelInfo } contentType title } } fragment fFilterOptions on FilterOptions { type remote categories { name title options { title id channelId } } } fragment fContentElementItem on ContentElementItem { id url info branding { ...fBrand } body config headline contentType channel { ...fChannelInfo } site picture { url } videoType orientation date duration flags genres valid { from to } epg { episode { ...fEpisode } season { ...fSeason } duration nextEpgInfo { ...fEpgInfo } } debug @include(if: $debug) { ...fContentDebugInfo } } fragment fContentDebugInfo on ContentDebugInfo { source transformations { description } } '}
        parameters.update({'variables': '{{"authentication":null,"contentType":"video","debug":false,"domain":"{0}","isMobile":false,"url":"{1}"}}'.format(domain, path)})
    else:
        parameters = {'query': ' query PreviewContentQuery($domain: String!, $url: String!, $date: DateTime, $contentType: String, $debug: Boolean!, $authentication: AuthenticationInput) { site(domain: $domain, date: $date, authentication: $authentication) { domain path(url: $url) { route { ...fRoute } page { ...fPage ...fVideoPage } content(type: PREVIEW, contentType: $contentType) { ...fContent } mainNav: navigation(type: MAIN) { items { ...fNavigationItem } } metaNav: navigation(type: META) { items { ...fNavigationItem } } channelNav: navigation(type: CHANNEL) { items { ...fNavigationItem } } showsNav: navigation(type: SHOWS) { items { ...fNavigationItem } } footerNav: navigation(type: FOOTER) { items { ...fNavigationItem } } networkNav: navigation(type: NETWORK) { items { ...fNavigationItem } } } } } fragment fRoute on Route { url exists authentication comment contentType name cmsId startDate status endDate } fragment fPage on Page { cmsId contentType pagination { ...fPagination } title shortTitle subheadline proMamsId additionalProMamsIds route source regWall { ...fRegWall } links { ...fLink } metadata { ...fMetadata } breadcrumbs { id href title text } channel { ...fChannel } seo { ...fSeo } modified published flags mainClassNames } fragment fPagination on Pagination { kind limit parent contentType } fragment fRegWall on RegWall { isActive start end } fragment fLink on Link { id classes language href relation title text outbound } fragment fMetadata on Metadata { property name content } fragment fChannel on Channel { name title shortName licenceTerms cssId cmsId proMamsId additionalProMamsIds route image hasLogo liftHeadings, logo sponsors { ...fSponsor } } fragment fSponsor on Sponsor { name url image } fragment fSeo on Seo { title keywords description canonical robots } fragment fVideoPage on VideoPage { ... on VideoPage { copyright description longDescription duration season episode airdate videoType contentResource image webUrl livestreamStartDate livestreamEndDate recommendation { results { headline subheadline duration url image videoType contentType recoVariation recoSource channel { ...fChannelInfo } } } } } fragment fChannelInfo on ChannelInfo { title shortName cssId cmsId } fragment fContent on Content { areas { ...fContentArea } } fragment fContentArea on ContentArea { id containers { ...fContentContainer } filters { ...fFilterOptions } debug @include(if: $debug) { ...fContentDebugInfo } } fragment fContentContainer on ContentContainer { id style elements { ...fContentElement } } fragment fContentElement on ContentElement { id authentication title description component config style highlight navigation { ...fNavigationItem } regwall filters { ...fFilterOptions } update styleModifiers groups { id title total cursor itemSource { type id } items { ...fContentElementItem } debug @include(if: $debug) { ...fContentDebugInfo } } groupLayout debug @include(if: $debug) { ...fContentDebugInfo } } fragment fNavigationItem on NavigationItem { selected href channel { ...fChannelInfo } contentType title items { selected href channel { ...fChannelInfo } contentType title } } fragment fFilterOptions on FilterOptions { type remote categories { name title options { title id channelId } } } fragment fContentElementItem on ContentElementItem { id url info branding { ...fBrand } body config headline contentType channel { ...fChannelInfo } site picture { url } videoType orientation date duration flags genres valid { from to } epg { episode { ...fEpisode } season { ...fSeason } duration nextEpgInfo { ...fEpgInfo } } debug @include(if: $debug) { ...fContentDebugInfo } } fragment fBrand on Brand { id, name } fragment fEpisode on Episode { number } fragment fSeason on Season { number } fragment fEpgInfo on EpgInfo { time endTime primetime } fragment fContentDebugInfo on ContentDebugInfo { source transformations { description } } '}
        parameters.update({'variables': '{{"authentication":null,"contentType":"livestream24","debug":false,"domain":"{0}","isMobile":false,"url":"{1}"}}'.format(domain, path)})
    url = '{0}{1}?{2}'.format(base, path, urllib.urlencode(parameters).replace('+', '%20'))
    xbmc.log('url = {0}'.format(url))
    result = requests.get(url).json()
    if result and path.endswith('/video') and result.get('data', None) and result.get('data').get('site', None) and result.get('data').get('site').get('path', None) and result.get('data').get('site').get('path').get('route').get('status').lower() == 'not_found':
        result = getContentPreview(domain, '{0}s'.format(path))
    return result


def getPagination(domain, path, cursor):
    base = 'https://magellan-api.p7s1.io/pagination/{0}/{1}/graphql'.format(domain, path)
    parameters = {'query': ' query QueryItems($domain: String!, $elementId: String!, $channelContext: String, $groupId: String, $cursor: String, $filter: FilterStateInputType, $limit: Int, $debug: Boolean!, $authentication: AuthenticationInput) { site(domain: $domain, authentication: $authentication) { items(element: $elementId, channelContext: $channelContext, group: $groupId, cursor: $cursor, filter: $filter, limit: $limit) { id title total cursor itemSource { type id } items { ...fContentElementItem } debug @include(if: $debug) { ...fContentDebugInfo } } } } fragment fContentElementItem on ContentElementItem { id listIndex url target foldOut info branding { ...fBrand } body config headline contentType channel { ...fChannelInfo } site picture { url } pictures { url dimension name title copyright description orientation imageOverlayTarget imageOverlayType kicker } candidate { firstName teamName headline cssId contestantType status comments { threadId } voting { result { candidateCmsId voteCount dimensions ranking } userVote } linkedPersons: linkedPersonsAny } product { price displayedPrice productLink } videoType orientation date duration flags genres valid { from to } epg { episode { ...fEpisode } season { ...fSeason } duration nextEpgInfo { ...fEpgInfo } } debug @include(if: $debug) { ...fContentDebugInfo } } fragment fBrand on Brand { id, name } fragment fChannelInfo on ChannelInfo { title shortName cssId cmsId } fragment fEpisode on Episode { number } fragment fSeason on Season { number } fragment fEpgInfo on EpgInfo { time endTime primetime branding { name } } fragment fContentDebugInfo on ContentDebugInfo { source transformations { description } } '}
    parameters.update({'variables': '{{"authentication":null,"cursor":"{0}","debug":false,"domain":"{1}","elementId":"{2}","limit":18}}'.format(cursor, domain, path)})
    url = '{0}?{1}'.format(base, urllib.urlencode(parameters).replace('+', '%20'))
    url = '{0}&queryhash={1}'.format(url, sha256(url.encode('utf-8')).hexdigest())
    xbmc.log('url = {0}'.format(url))
    result = requests.get(url).json()
    return result


def getLiveevents(domain, std):
    url = 'https://middleware.7tv.de/ran-mega/mobile/v1/livestreams.json'
    result = requests.get(url, headers={'Accept-Encoding': 'gzip'}).json()
    return result
    #base = 'https://magellan-api.p7s1.io/epg-mini/{0}/graphql'.format(domain)
    #parameters = {'query': ' query EpgQuery($domain: String!, $date: DateTime, $subBrand: String) { site(domain: $domain) { epgs { upcoming: broadcast(type: UPCOMING, date: $date, subBrand: $subBrand) { items { ...fEpgItem } } primetime: broadcast(type: PRIMETIME, date: $date, subBrand: $subBrand) { items { ...fEpgItem } } primenight: broadcast(type: PRIMENIGHT, date: $date, subBrand: $subBrand) { items { ...fEpgItem } } } } } fragment fEpgItem on EpgItem { id title description startTime endTime episode { number } season { number } tvShow { title id } images { url title copyright } links { href contentType title } } '}
    #parameters.update({'variables': '{{"date":"{0}","domain":"{1}"}}'.format(std, domain)})
    #url = '{0}?{1}'.format(base, urllib.urlencode(parameters).replace('+', '%20'))
    #url = '{0}&queryhash={1}'.format(url, sha256(url.encode('utf-8')).hexdigest())
    #xbmc.log('url = {0}'.format(url))
    #result = requests.get(url).json()
    #return result


def getListItems(data, type, domain=None, path=None, cmsId=None, content=None):
    if not content:
        content = {'items': []}

    if type == 'season':
        subcontent = getContentPreview(domain, path)
        content = getShownav(subcontent.get('data', None), content, domain, cmsId)

    if (len(content.get('items')) == 0 or content.get('type') == 'episode') and data.get('site', None) and data.get('site').get('path', None) and data.get('site').get('path').get('content', None) and data.get('site').get('path').get('content').get('areas', None):
        areas = data.get('site').get('path').get('content').get('areas')
        if len(areas) > 0:
            containers = areas[0].get('containers')
            for container in containers:
                elements = container.get('elements', None)
                if elements and len(elements) > 0:
                    element = elements[0]
                    groups = element.get('groups', None)
                    if groups and len(groups) > 0:
                        groupitems = groups[0].get('items', None)
                        if groupitems:
                            for groupitem in groupitems:
                                if groupitem:
                                    citems = content.get('items')
                                    if type == 'show':
                                        item = getContentInfos(groupitem, 'show')
                                        if checkItemUrlExists(citems, item) == False:
                                            citems.append(item)
                                            content.update({'items': citems})
                                    elif cmsId and groupitem.get('channel').get('cmsId') == cmsId:
                                        if not groupitem.get('videoType') and groupitem.get('headline') and (groupitem.get('headline').lower().startswith('staffel') or groupitem.get('headline').lower().startswith('season')):
                                            content.update({'type': 'season'})
                                            item = getContentInfos(groupitem, 'season')
                                            if checkItemUrlExists(citems, item) == False:
                                                citems.append(item)
                                                content.update({'items': citems})
                                        elif (groupitem.get('videoType') and groupitem.get('videoType').lower() == 'full') \
                                             or (not groupitem.get('videoType') and groupitem.get('url') and groupitem.get('url').startswith(path) and groupitem.get('url').find('playlist') == -1 and groupitem.get('url').find('clip') == -1):
                                            content.update({'type': 'episode'})
                                            item = getContentInfos(groupitem, 'episode')
                                            if checkItemUrlExists(citems, item) == False:
                                                citems.append(item)
                                                content.update({'items': citems})

    if not content.get('type'):
        content.update({'type': type})

    return content


def getShownav(data, content, domain, cmsId):
    if data.get('site', None) and data.get('site').get('path', None) and data.get('site').get('path').get('channelNav', None) and data.get('site').get('path').get('channelNav').get('items', None):
        channelitems = data.get('site').get('path').get('channelNav').get('items')
        for channelitem in channelitems:
            if channelitem.get('title').lower() == 'video' or channelitem.get('title').lower() == 'videos':
                for channelsubitem in channelitem.get('items'):
                    if channelsubitem.get('title').lower().find('staffel') > -1 or channelsubitem.get('title').lower().find('season') > -1:
                        content.update({'type': 'season', 'cmsId': channelitem.get('channel').get('cmsId')})
                        citems = content.get('items')
                        citems.append(getContentInfos(channelsubitem, 'season'))
                        content.update({'items': citems})
                    elif channelsubitem.get('title').lower().find('episode') > -1 or channelsubitem.get('title').lower().find('folge') > -1:
                        subcontent = getContentFull(domain, channelsubitem.get('href'))
                        content = getListItems(subcontent.get('data'), 'episode', domain, channelsubitem.get('href'), cmsId, content)
                        content.update({'type': 'episode'})

    return content


def getContentInfos(data, type):
    infos = {}
    if type == 'live':
        now_item = None
        next_item = None
        for index, item in enumerate(data.get('items')):
            now = datetime.utcnow()

            start_time = datetime.fromtimestamp(time.mktime(time.strptime(item.get('startTime'), '%Y-%m-%dT%H:%M:%S.%fZ')))
            end_time = datetime.fromtimestamp(time.mktime(time.strptime(item.get('endTime'), '%Y-%m-%dT%H:%M:%S.%fZ')))

            infos.update({'stime': start_time})
            infos.update({'etime': end_time})
            if (now >= start_time) and (now <= end_time):
                now_item = item
                next_item = data.get('items')[index + 1]
                break

        if now_item:
            infoLabels = {'title': now_item.get('title')}
            if now_item.get('tvShow'):
                if not infoLabels.get('title'):
                    infoLabels.update({'title': now_item.get('tvShow').get('title')})
                infoLabels.update({'tvShowTitle': now_item.get('tvShow').get('title')})
                infoLabels.update({'mediatype': 'episode'})

            if now_item.get('season').get('number') and int(now_item.get('season').get('number')) > 0:
                infoLabels.update({'season': now_item.get('season').get('number')})
            if now_item.get('episode').get('number') and int(now_item.get('episode').get('number')) > 0:
                infoLabels.update({'episode': now_item.get('episode').get('number')})

            local_start_time = utc_to_local(infos.get('stime'))
            local_end_time = utc_to_local(infos.get('etime'))
            plot = '{0} - {1}'.format(local_start_time.strftime('%H:%M'), local_end_time.strftime('%H:%M'))
            if next_item:
                next_title = next_item.get('title') if next_item.get('title') else None
                next_show = next_item.get('tvShow').get('title') if next_item.get('tvShow') else ''

                plot = '{0}{1}'.format(plot, '\nDanach: [COLOR blue]{0}[/COLOR] {1}'.format(next_show, next_title) if next_title and next_show != '' and next_title != next_show else '\nDanach: {0}'.format(next_title if next_title else next_show))

            plot = '{0}\n\n'.format(plot)
            plot = '{0}{1}'.format(plot, now_item.get('description') if now_item.get('description') else '')
            infoLabels.update({'plot': plot})

            if now_item.get('images') and len(now_item.get('images')) > 0:
                art = {'thumb': '{0}{1}'.format(now_item.get('images')[0].get('url'), '/profile:mag-648x366')}
                infos.update({'art' : art})

            infos.update({'infoLabels' : infoLabels})
    else:
        infos.update({'url': data.get('url') if data.get('url') else data.get('href'), 'type': type, 'contentType': data.get('contentType')})

        if type == 'episode':
            title = data.get('headline')
            if title.find('Originalversion') > -1:
                title = title.replace('Originalversion', 'OV')
            if (title.lower().find('episode') > -1 or title.lower().find('folge') > -1) and title.find(':') > -1:
                splits = title.split(':', 1)
                for split in splits:
                    if split.lower().find('episode') == -1 and split.lower().find('folge') == -1:
                        title = split.strip()
                        break
            infoLabels = {'title': title}
            infoLabels.update({'tvShowTitle': data.get('channel').get('title')})
            season_match = re.search('(staffel|season)[\S](\d+)', infos.get('url'))
            if season_match:
                infoLabels.update({'season': int(season_match.group(2))})
            episode_match = re.search('(episode|folge)\S(\d+)', infos.get('url'))
            if episode_match:
                infoLabels.update({'episode': int(episode_match.group(2))})
            if not infoLabels.get('season'):
                season = data.get('epg').get('season').get('number')
                if season and season.startswith('s'):
                    season = season.split('s', 1)[1]
                if season:
                    infoLabels.update({'season': int(season)})
            if not infoLabels.get('episode'):
                episode = data.get('epg').get('episode').get('number')
                if episode and episode.startswith('e'):
                    episode = episode.split('e', 1)[1]
                if episode:
                    infoLabels.update({'episode': int(episode)})
            infoLabels.update({'duration': data.get('epg').get('duration')})
            infoLabels.update({'mediatype': 'episode'})
        elif type == 'season':
            title = data.get('headline') if data.get('headline') else data.get('title')
            if title.find(':') > -1:
                splits = title.split(':')
                for split in splits:
                    if split.lower().find('staffel') > -1 or split.lower().find('season') > -1:
                        title = split.strip()
                        break
            infoLabels = {'title': title}
            season_match = re.search('staffel[\S\s]+(\d+)|season[\S\s]+(\d+)', title.lower())
            if not season_match:
                season_match = re.search('(\d+)[\S\s]+staffel|(\d+)[\S\s]+season', title.lower())
            if season_match:
                infoLabels.update({'season': int(season_match.group(1))})

        elif type == 'show':
            infoLabels = {'title': data.get('channel').get('shortName') if data.get('channel').get('shortName') else data.get('headline')}
            infos.update({'cmsId': data.get('id')})

        infoLabels.update({'plot': data.get('info') if data.get('info') else None})
        infos.update({'infoLabels' : infoLabels})

        if data.get('picture'):
            art = {'thumb': '{0}{1}'.format(data.get('picture').get('url'), '/profile:mag-648x366')}
            infos.update({'art' : art})

    return infos


def utc_to_local(utc_dt):
    # get integer timestamp to avoid precision lost
    timestamp = calendar.timegm(utc_dt.timetuple())
    local_dt = datetime.fromtimestamp(timestamp)
    assert utc_dt.resolution >= timedelta(microseconds=1)
    return local_dt.replace(microsecond=utc_dt.microsecond)


def getVideoId(data):
    videoid = None
    if data.get('site', None) and data.get('site').get('path', None) and data.get('site').get('path').get('page', None):
        page = data.get('site').get('path').get('page')
        videoid = page.get('contentResource')[0].get('id')

    return videoid


def playVideo(entry):
    # Inputstream and DRM
    helper = Helper(protocol='mpd', drm='widevine')
    isInputstream = helper.check_inputstream()
    if isInputstream == False:
        return

    access_token = 'seventv-web'
    salt = '01!8d8F_)r9]4s[qeuXfP%'
    client_name = ''
    
    content = getContentPreview(entry.get('domain'), entry.get('path'))
    if content:
        video_id = getVideoId(content.get('data'))

    json_url = 'http://vas.sim-technik.de/vas/live/v2/videos/{0}?{1}'.format(video_id, urllib.urlencode({
            'access_token': access_token,
            'client_location': entry.get('path'),
            'client_name': client_name
        }))
    json_data = requests.get(json_url).json()

    source_id = 0
    for stream in json_data.get('sources'):
        if stream.get('mimetype') == 'application/dash+xml':
            if int(source_id) < int(stream.get('id')):
                source_id = stream.get('id')

    client_id_1 = '{0}{1}'.format(salt[:2], sha1('{0}{1}{2}{3}{4}{5}'.format(video_id, salt, access_token, entry.get('path'), salt, client_name).encode('utf-8')).hexdigest())

    json_url = 'https://vas.sim-technik.de/vas/live/v2/videos/{0}/sources?{1}'.format(video_id, urllib.urlencode({
        'access_token':  access_token,
        'client_location':  entry.get('path'),
        'client_name':  client_name,
        'client_id': client_id_1
    }))
    json_data = requests.get(json_url).json()
    server_id = json_data.get('server_id')

    client_id = '{0}{1}'.format(salt[:2], sha1('{0}{1}{2}{3}{4}{5}{6}{7}'.format(salt, video_id, access_token, server_id, entry.get('path'), source_id, salt, client_name).encode('utf-8')).hexdigest())
    url_api_url = 'http://vas.sim-technik.de/vas/live/v2/videos/{0}/sources/url?{1}'.format(video_id, urllib.urlencode({
        'access_token': access_token,
        'client_id': client_id,
        'client_location': entry.get('path'),
        'client_name': client_name,
        'server_id': server_id,
        'source_ids': str(source_id),
    }))

    json_data = requests.get(url_api_url).json()
    for stream in json_data.get('sources'):
        data = stream.get('url')

    li = xbmcgui.ListItem(path='{0}|{1}'.format(data, userAgent))
    li.setProperty('inputstream.adaptive.license_type', 'com.widevine.alpha')
    li.setProperty('inputstream.adaptive.manifest_type', 'mpd')
    li.setProperty('inputstreamaddon' if kodiVersion <= 18 else 'inputstream', 'inputstream.adaptive')
    
    if json_data.get('drm') and json_data.get('drm').get('licenseAcquisitionUrl') and json_data.get('drm').get('token'):
        drm_lic = json_data.get('drm').get('licenseAcquisitionUrl')
        drm_token = json_data.get('drm').get('token')
        li.setProperty('inputstream.adaptive.license_key', '{0}?token={1}|{2}|{3}|'.format(drm_lic, drm_token, userAgent, 'R{SSM}'))

    if entry.get('infoLabels') and len(entry.get('infoLabels')) > 0:
        li.setInfo('video', entry.get('infoLabels'))

    xbmcplugin.setResolvedUrl(addon_handle, True, li)


def playLive(entry):
    # Inputstream and DRM
    helper = Helper(protocol='mpd', drm='widevine')
    if helper.check_inputstream() == False:
        return

    url = 'https://vas-live-mdp.glomex.com/live/1.0/getprotocols?{0}'.format(urllib.urlencode({
        'access_token': entry.get('access_token'),
        'client_location':  entry.get('client_location'),
        'property_name':  entry.get('property_name'),
        'client_token':  entry.get('client_token'),
        'secure_delivery': 'true'
    }))

    data = requests.get(url).json()

    server_token = data.get('server_token')
    salt = entry.get('salt', '01!8d8F_)r9]4s[qeuXfP%')
    protokol = 'dash'
    if 'widevine' in data.get('protocols').get(protokol).get('drm'):
        protokol_drm = 'widevine'
        protokol_param = '{0}:{1}'.format(protokol, protokol_drm)
    else:
        protokol_drm = 'clear'
        protokol_param = protokol
    client_token = '{0}{1}'.format(salt[:2], sha1('{0}{1}{2}{3}{4}{5}'.format(entry.get('property_name'), salt, entry.get('access_token'), server_token, entry.get('client_location'), protokol_param).encode('utf-8')).hexdigest())

    url = 'https://vas-live-mdp.glomex.com/live/1.0/geturls?{0}'.format(urllib.urlencode({
        'access_token':  entry.get('access_token'),
        'client_location':  entry.get('client_location'),
        'property_name':  entry.get('property_name'),
        'protocols': protokol_param,
        'server_token': server_token,
        'client_token': client_token,
        'secure_delivery': 'true'
    }))

    json_data = requests.get(url).json()
    drm_data = json_data.get('urls').get(protokol).get(protokol_drm)

    li = xbmcgui.ListItem(path='{0}|{1}'.format(drm_data.get('url'), userAgent))
    li.setProperty('inputstream.adaptive.license_type', 'com.widevine.alpha')
    li.setProperty('inputstream.adaptive.manifest_type', 'mpd')
    if addon.getSetting('sync_timing') == 'true':
        li.setProperty('inputstream.adaptive.manifest_update_parameter', 'full')
    li.setProperty('inputstreamaddon' if kodiVersion <= 18 else 'inputstream', 'inputstream.adaptive')

    if drm_data.get('drm') and drm_data.get('drm').get('licenseAcquisitionUrl') and drm_data.get('drm').get('token'):
        drm_lic = drm_data.get('drm').get('licenseAcquisitionUrl')
        drm_token = drm_data.get('drm').get('token')
        li.setProperty('inputstream.adaptive.license_key', '{0}?token={1}|{2}|{3}|'.format(drm_lic, drm_token, userAgent, 'R{SSM}'))

    xbmcplugin.setResolvedUrl(addon_handle, True, li)


def rootDir():
    rootDirs = json.load(py2_decode(open('{0}/resources/root.json'.format(addonPath))))
    for dir in rootDirs:
        if not dir.get('channels'):
            url = build_url({'action': dir.get('action')})
            addDir(label=dir.get('label'), url=url)
        else:
            channels = dir.get('channels')
            for channel in channels:
                if channel.get('art'):
                    for artkey in channel.get('art').keys():
                        channel.get('art').update({artkey: os.path.join(addonPath, channel.get('art').get(artkey))})
                parameter = {'action': channel.get('action', 'shows'), 'entry': channel}
                addDir(label=channel.get('label'), url=build_url(parameter), art=channel.get('art'))

    xbmcplugin.endOfDirectory(addon_handle, cacheToDisc=True)


def listChildren(entry):
    for child in entry.get('children'):
        art = dict()
        if child.get('art'):
            for artkey in child.get('art').keys():
                art.update({artkey: os.path.join(addonPath, child.get('art').get(artkey))})

        infoLabels = dict()
        if child.get('plot'):
            infoLabels.update(dict(plot=child.get('plot')))
        label = child.get('label')
        if label.find('Live') >= 0:
            nt = time.time()
            number_livestreams = 0
            content = getLiveevents(None, None)
            for event in content.get('contents'):            
                if event.get('streamdate_end') >= nt and event.get('streamdate_start') <= nt:
                    number_livestreams += 1
            label = label.format(number_livestreams)
        parameter = {'action': child.get('action'), 'entry': child}
        addDir(label=label, url=build_url(parameter), art=art, infoLabels=infoLabels)

    xbmcplugin.endOfDirectory(addon_handle, cacheToDisc=True)


def listLiveChannels():
    channels = dict()
    rootDirs = json.load(py2_decode(open('{0}/resources/root.json'.format(addonPath))))
    for dir in rootDirs:
        if dir.get('channels'):
            channels = dir.get('channels')

    content = getContentPreview(channels[0].get('domain'), '/livestream')
    epg_data = None
    if content.get('data') and content.get('data').get('site') and content.get('data').get('site').get('path') and content.get('data').get('site').get('path').get('page') and content.get('data').get('site').get('path').get('page').get('epg'):
        epg_data = content.get('data').get('site').get('path').get('page').get('epg')

    contextmenuitems = [(('Aktualisieren', 'RunPlugin({0})'.format(build_url({'action': 'refresh'}))))]
    for channel in channels:
        thumbnailImage = None
        if channel.get('property_name', None) and epg_data:
            infoLabels = None
            art = None
            for epg in epg_data:
                if epg.get('name').lower() == channel.get('epg_name').lower():
                    infos = getContentInfos(epg, 'live')
                    infoLabels = infos.get('infoLabels')
                    art = infos.get('art')

            channel.update({'infoLabels': infoLabels, 'art': art})
            url = build_url({'action': 'playlive', 'entry': channel})
            title = infoLabels.get('title') if infoLabels.get('tvShowTitle', None) is None or infoLabels.get('tvShowTitle') == infoLabels.get('title') else '[COLOR blue]{0}[/COLOR] {1}'.format(infoLabels.get('tvShowTitle'), infoLabels.get('title'))
            title = '[COLOR orange]{0}[/COLOR] {1}'.format(channel.get('label'), title)
            addFile(title, url, art=art, infoLabels=infoLabels, contextMenuItems=contextmenuitems)

    xbmcplugin.setContent(addon_handle, 'files')
    xbmcplugin.endOfDirectory(addon_handle, cacheToDisc=False)


def listLiveevents(entry):
    contextmenuitems = [(('Aktualisieren', 'RunPlugin({0})'.format(build_url({'action': 'refresh'}))))]
    content = getLiveevents(None, None)
    events = sorted(content.get('contents'), key=lambda k: k.get('streamdate_start'))
    eventday = None;
    for event in events:
        sdt = datetime.fromtimestamp(event.get('streamdate_start'))
        edt = datetime.fromtimestamp(event.get('streamdate_end'))

        match_date = sdt.strftime('%d.%m.%Y')
        match_time = sdt.strftime('%H:%M')
        match_weekday = dayNames[sdt.weekday()]
        if eventday is None or eventday < sdt.date():
            eventday = sdt.date()
            addFile('[COLOR gold]{0}, {1}[/COLOR]'.format(match_weekday, match_date), None, art=dict(thumb='DefaultYear.png'), isPlayable=False)

        
        url = build_url({'action': 'liveitem', 'entry': dict(resource=event.get('resource'), st=event.get('streamdate_start'), et=event.get('streamdate_end'))})
        addFile('[COLOR red]{0}[/COLOR] {1}'.format(match_time, event.get('teaser').get('title')), url, contextMenuItems=contextmenuitems, art=dict(icon=event.get('teaser').get('image')))

    #xbmcplugin.setContent(addon_handle, 'files')
    xbmcplugin.endOfDirectory(addon_handle, cacheToDisc=False)



    #std = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    #content = getLiveevents(entry.get('domain'), std.strftime('%Y-%m-%dT%H:%M:%S.%fZ'))

    #contextmenuitems = [(('Aktualisieren', 'RunPlugin({0})'.format(build_url({'action': 'refresh'}))))]
    #if content.get('data') and content.get('data').get('site') and content.get('data').get('site').get('epgs') and content.get('data').get('site').get('epgs').get('upcoming'):
    #    events = content.get('data').get('site').get('epgs').get('upcoming').get('items')
    #    eventicon = os.path.join('{0}{1}'.format(addonPath, entry.get('art').get('icon')))
    #    eventday = None;
    #    for event in events:
    #        sdt = utc_to_local(datetime.strptime(event.get('startTime'), '%Y-%m-%dT%H:%M:%S.%fZ'))
    #        match_date = sdt.strftime('%d.%m.%Y')
    #        match_time = sdt.strftime('%H:%M')
    #        match_weekday = dayNames[sdt.weekday()]
    #        if eventday is None or eventday < sdt.date():
    #            eventday = sdt.date()
    #            addFile('[COLOR gold]{0}, {1}[/COLOR]'.format(match_weekday, match_date), None, art=dict(thumb='DefaultYear.png'), isPlayable=False)

    #        url = ''#build_url({'action': 'playlive', 'entry': channel})
    #        addFile('[COLOR red]{0}[/COLOR] {1}'.format(match_time, event.get('title')), url, contextMenuItems=contextmenuitems, art=dict(icon=eventicon))

    #xbmcplugin.setContent(addon_handle, 'files')
    #xbmcplugin.endOfDirectory(addon_handle, cacheToDisc=False)


def build_liveitem(entry):
    nt = time.time()
    if entry.get('st') > nt or entry.get('et') < nt:
        if entry.get('st') > nt:
            msg = 'noch nicht'
        else:
            msg = 'nicht mehr'
        msg = 'Der Stream ist {0} verfügbar'.format(msg)
        xbmcgui.Dialog().ok(addon.getAddonInfo('name'), msg)
        xbmcplugin.setResolvedUrl(addon_handle, False, xbmcgui.ListItem())
        return False

    url = '{0}{1}'.format('https://middleware.7tv.de', entry.get('resource'))
    result = requests.get(url, headers={'Accept-Encoding': 'gzip'}).json()

    stream_url = result.get('stream_url')
    salt = '01iegahthei8yok0Eopai6jah5Qui0qu'
    access_token = 'ran-app'
    location = 'https://app.ran.de/{0}'.format(stream_url)
    client_token = '{0}{1}'.format(salt[:2], sha1('{0}{1}{2}{3}'.format(stream_url, salt, access_token, location).encode('utf-8')).hexdigest())
    item = dict(access_token=access_token, client_location=location, property_name=stream_url, client_token=client_token, salt=salt)
    playLive(item)


def addDir(label, url, art={}, infoLabels={}):
    addFile(label=label, url=url, art=art, infoLabels=infoLabels, isFolder=True, isPlayable=False)


def addFile(label, url, art={}, infoLabels={}, contextMenuItems=[], isFolder=False, isPlayable=True):
    li = xbmcgui.ListItem(label)
    if infoLabels or isPlayable:
        li.setInfo('video', infoLabels)
    li.setArt(art)
    if isPlayable == True:
        li.setProperty('IsPlayable', str(isPlayable))
    if len(contextMenuItems) > 0:
        li.addContextMenuItems(contextMenuItems)

    xbmcplugin.addDirectoryItem(handle=addon_handle, url=url, listitem=li, isFolder=isFolder)


def build_url(query):
    return '{0}?{1}'.format(pluginBaseUrl, base64.urlsafe_b64encode(json.dumps(query).encode('utf-8')).decode('utf-8'))


def build_video(item, domain):
    art = dict()
    if item.get('picture'):
        art.update(dict(poster='{0}/profile:mag-648x366'.format(item.get('picture').get('url'))))

    infoLabels = dict()
    if item.get('info'):
        infoLabels.update(dict(plot=item.get('info')))
    if item.get('duration'):
        infoLabels.update(dict(duration=item.get('duration')))
    if item.get('valid', {}).get('to'):
        try:
            edt = datetime.strptime(item.get('valid').get('to'), '%Y-%m-%dT%H:%M:%S.%fZ')
        except TypeError:
            edt = datetime(*(time.strptime(item.get('valid').get('to'), '%Y-%m-%dT%H:%M:%S.%fZ')[0:6]))
        edt = utc_to_local(edt)
        plot = '[COLOR red]Verfügbar bis {0} {1} Uhr[/COLOR]\n\n{2}'.format(edt.strftime('%d.%m.%Y'), edt.strftime('%H:%M'), infoLabels.get('plot'))
        infoLabels.update(dict(plot=plot))

    label = item.get('headline')
    if item.get('valid', {}).get('from'):
        try:
            sdt = datetime.strptime(item.get('valid').get('from'), '%Y-%m-%dT%H:%M:%S.%fZ')
        except TypeError:
            sdt = datetime(*(time.strptime(item.get('valid').get('from'), '%Y-%m-%dT%H:%M:%S.%fZ')[0:6]))
        sdt = utc_to_local(sdt)
        label = '[COLOR blue]{0}[/COLOR] {1}'.format(sdt.strftime('%d.%m.%Y'), label)
    
    url = build_url({'action': 'play', 'entry': dict(domain=domain, path=item.get('url'))})
    addFile(label=label, url=url, art=art, infoLabels=infoLabels)


def build_pagination_dir(domain, path, cursor, page):
    url = build_url({'action': 'pagination', 'entry': dict(domain=domain, path=path, cursor=cursor, page=page)})
    addDir(label='--- Weiter zu Seite {0} ---'.format(page), url=url)


def checkItemUrlExists(items, compItem):
    for item in items:
        if item.get('url') == compItem.get('url'):
            return True

    return False


params = urllib.unquote(sys.argv[2][1:])
if len(params) > 0:
    if len(params) % 4 != 0:
        params = '{0}{1}'.format(params, '=' * (4 - len(params) % 4))

    params = dict(json.loads(base64.urlsafe_b64decode(py2_encode(params))))
xbmc.log('params = {0}'.format(params))
if 'action' in params:
    action = params.get('action')
    if action == 'livechannels':
        listLiveChannels()
    elif action == 'liveevents':
        listLiveevents(params.get('entry'))
    elif action == 'liveitem':
        build_liveitem(params.get('entry'))
    elif action == 'shows':
        listShows(params.get('entry'))
    elif action == 'showcontent':
        listShowcontent(params.get('entry'))
    elif action == 'subdirs':
        listChildren(params.get('entry'))
    elif action == 'videostruct':
        listVideostruct(params.get('entry'))
    elif action == 'videos':
        listVideos(params.get('entry'), params.get('folder'))
    elif action == 'pagination':
        listPaginationVideos(params.get('entry'))
    elif action == 'play':
        playVideo(params.get('entry'))
    elif action == 'playlive':
        playLive(params.get('entry'))
    elif action == 'refresh':
        xbmc.executebuiltin("Container.Refresh")
else:
    rootDir()
