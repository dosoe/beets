# -*- coding: utf-8 -*-
# This file is part of beets.
# Copyright 2017, Dorian Soergel.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

"""Gets work title, disambiguation, parent work and its disambiguation,
composer, composer sort name and performers
"""

from __future__ import division, absolute_import, print_function

from beets import ui
from beets.plugins import BeetsPlugin

import musicbrainzngs


def work_father(work_id):
    """ This function finds the id of the father work given its id"""
    work_info = musicbrainzngs.get_work_by_id(work_id,
                                              includes=["work-rels"])
    if 'work-relation-list' in work_info['work']:
        for work_father in work_info['work']['work-relation-list']:
            if work_father['type'] == 'parts' \
                    and work_father.get('direction') == 'backward':
                father_id = work_father['work']['id']
                return(father_id)
        return(None)

    else:
        return(None)


def work_parent(work_id):
    """This function finds the parentwork id of a work given its id. """
    while True:
        new_work_id = work_father(work_id)
        if not new_work_id:
            return work_id
            break
        work_id = new_work_id
    return work_id


def find_parentwork(work_id):
    """This function gives the work relationships (dict) of a parent_work
    given the id of the work"""
    parent_id = work_parent(work_id)
    work_info = musicbrainzngs.get_work_by_id(parent_id,
                                              includes=["artist-rels"])
    return(work_info)


class ParentWorkPlugin(BeetsPlugin):

    def __init__(self):
        super(ParentWorkPlugin, self).__init__()
        self.import_stages = [self.imported]
        self.config.add({
            u'bin': u'parentwork',
            u'auto': True,
            u'force': False,
        })

        if self.config['auto'].get(bool):
            self.import_stages = [self.imported]

    def commands(self):
        cmd = ui.Subcommand('parentwork',
                            help=u'fetches parent works, composers \
                                and performers')
        cmd.parser.add_option(
            u'-f', u'--force', dest='force_refetch',
            action='store_true', default=False,
            help=u'always re-fetch works',
        )

        def func(lib, opts, args):
            for item in lib.items(ui.decargs(args)):
                self.find_work(
                    lib, item,
                    opts.force_refetch or self.config['force'],
                )

        cmd.func = func
        return [cmd]

    def command(self, lib, opts, args):
        self.find_work(lib.items(ui.decargs(args)))

    def imported(self, session, task):
        """Import hook for fetching parentworks automatically.
        """
        if self.config['auto']:
            for item in task.imported_items():
                self.find_work(session.lib, item,
                               self.config['force'])

    def get_info(self, item, work_info, parent_composer, parent_composer_sort,
                 parent_work, parent_work_disambig, dupe_ids, composer_ids):
        """Given the parentwork info dict, this function updates parent_composer,
        parent_composer_sort, parent_work, parent_work_disambig, work_ids and
        composer_ids"""
        composer_exists = False
        if 'artist-relation-list' in work_info['work']:
            for artist in work_info['work']['artist-relation-list']:
                if artist['type'] == 'composer':
                    composer_exists = True
                    if artist['artist']['id'] not in composer_ids:
                        composer_ids.add(artist['artist']['id'])
                        parent_composer.append(artist['artist']['name'])
                        parent_composer_sort.append(artist['artist']
                                                    ['sort-name'])
        if not composer_exists:
            self._log.info(item.artist + ' - ' + item.title)
            self._log.info(
                "no composer, add one at https://musicbrainz.org/work/" +
                work_info['work']['id'])
        if work_info['work']['id'] in dupe_ids:
            pass
        else:
            parent_work.append(work_info['work']['title'])
            dupe_ids.add(work_info['work']['id'])
            if 'disambiguation' in work_info['work']:
                parent_work_disambig.append(work_info['work']
                                            ['disambiguation'])

    def find_work(self, lib, item, force):

        parent_work          = []
        parent_work_disambig = []
        parent_composer      = []
        parent_composer_sort = []
        dupe_ids             = set()
        composer_ids         = set()

        item.read()
        recording_id = item.mb_trackid

        hasawork = True
        if not item.work_id:
            self._log.info("No work attached, recording id: " + recording_id)
            self._log.info(item.artist + ' - ' + item.title)
            self._log.info("add one at https://musicbrainz.org" +
                           "/recording/" + recording_id)
            hasawork = False
        found = True
        if (force or not parent_work) and hasawork:
            try:
                work_ids = item.work_id.split(', ')
                for w_id in work_ids:
                    work_info = find_parentwork(w_id)
                    self.get_info(item, work_info, parent_composer,
                                  parent_composer_sort, parent_work,
                                  parent_work_disambig,
                                  dupe_ids, composer_ids)
            except musicbrainzngs.musicbrainz.WebServiceError:
                self._log.debug("Work unreachable")
                found = False
        elif parent_work:
            self._log.debug("Work already in library, not necessary fetching")
            return

        if found:
            self._log.debug("Finished searching work for: " +
                            item.artist + ' - ' + item.title)
            self._log.debug("Work fetched: " + u', '.join(parent_work) +
                            ' - ' + u', '.join(parent_composer))
            item['parent_work']          = u', '.join(parent_work)
            item['parent_work_disambig'] = u', '.join(parent_work_disambig)
            item['parent_composer']      = u', '.join(parent_composer)
            item['parent_composer_sort'] = u', '.join(parent_composer_sort)

            item.store()
