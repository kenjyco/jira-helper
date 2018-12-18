# Pass JQL queries to JIRA server and filter results
#   - https://id.atlassian.com/manage/api-tokens create API token first
#   - https://developer.atlassian.com/server/jira/platform/jira-rest-api-examples/

import os
import urllib
import requests
import ujson
import re
import settings_helper as sh
import input_helper as ih
import redis_helper as rh
import dt_helper as dh
from io import StringIO
from functools import partial
from collections import OrderedDict
from chloop import GetCharLoop
from pprint import pprint


get_setting = sh.settings_getter(__name__)
JIRA_URL = get_setting('JIRA_URL')
JIRA_API_TOKEN = get_setting('JIRA_API_TOKEN')
JIRA_API_USER = get_setting('JIRA_API_USER')
PROJECTS = get_setting('PROJECTS')
ISSUE_TYPES = get_setting('ISSUE_TYPES')
STATUS_TYPES = get_setting('STATUS_TYPES')
RETURN_FIELDS = get_setting('RETURN_FIELDS')
ORDER_BY_FIELDS = get_setting('ORDER_BY_FIELDS')
DATE_RX = re.compile(r'\d{4}-\d{2}-\d{2}')

ALLOWED_FIELD_TYPE_INFO = {
    'return': {
        'fields': RETURN_FIELDS,
        'prompt': 'Select return fields you are interested in (separate by space)'

    },
    'orderby': {
        'fields': ORDER_BY_FIELDS,
        'prompt': 'Select order by fields you are interested in (separate by space)'
    }
}

SELECTED_FIELDS = rh.Collection(
    'jira',
    'fields',
    index_fields='name,type',
    json_fields='selected',
    rx_type='(return|orderby)'
)

SAVED_QUERIES = rh.Collection(
    'jira',
    'queries',
    index_fields='name',
)


def get_session():
    """Return an authenticated session object"""
    if not JIRA_URL or not JIRA_API_TOKEN or not JIRA_API_USER:
        raise Exception(
            '\nPlease define JIRA_URL, JIRA_API_TOKEN, and JIRA_API_USER environment vars..\n\n'
            'Visit https://confluence.atlassian.com/cloud/api-tokens-938839638.html to '
            'create an API token for your JIRA user if you have not already done so.'
        )
    session = requests.Session()
    session.auth = (JIRA_API_USER, JIRA_API_TOKEN)
    return session


def jql_search(jql, session=None, count=False, fields='', return_raw=False):
    """Pass jql query to jira and parse results

    - jql: string containing jql query text
    - session: an authenticated session object for jira
    - count: if True, return the total number of matching issues ONLY
    - fields: a comma-separated string of fields/subfields to be returned
        - i.e. "creator.displayName, status.name, description"
    - return_raw: if True, return the raw JSON response from JIRA, otherwise
      return the filtered data via `_filter_result_data` func
    """
    session = session or get_session()
    if count:
        fields = 'created'
    try:
        fields = ih.string_to_list(fields)
    except TypeError:
        if type(fields) in (list, tuple):
            pass
        else:
            raise
    fields_for_jql = ','.join([ f.split('.')[0] for f in fields ])
    url = JIRA_URL + '/rest/api/2/search?jql=' + urllib.parse.quote(jql)
    if fields_for_jql:
        url = url + '&fields=' + fields_for_jql
    response = session.get(url)
    full_json = None
    if response.ok and 'json' in response.headers['content-type']:
        full_json = response.json()
    else:
        if response.status_code == 400:
            errors = ujson.loads(ih.decode(response.content)).get('errorMessages')
            print('\n'.join(errors))
            return
        else:
            import pdb; pdb.set_trace()
            print('inspect the "response" object')
            return

    if count:
        return full_json['total']

    #
    #
    print('startAt:', full_json['startAt'])
    print('maxResults:', full_json['maxResults'])
    print('total:', full_json['total'])
    #
    #
    if return_raw:
        return full_json

    return _filter_result_data(full_json, *fields)


def _filter_result_data(results, *subfields):
    """Filter the raw JSON results returned from `jql_search` func

    - results: dict returned by `jql_search` func (when return_raw=True)
    - subfields: i.e. "creator.displayName", "status.name", "summary"
    """
    final_results = []
    nested_fields = []
    simple_fields = []
    for field in subfields:
        if '.' in field:
            nested_fields.append(field)
        else:
            simple_fields.append(field)

    for issue in results['issues']:
        this_issue = {'key': issue['key']}
        for field in simple_fields:
            this_issue[field] = issue['fields'].get(field)

        for field in nested_fields:
            f, parts = field.split('.', maxsplit=1)
            obj = issue['fields'].get(f, {})
            if obj is not None:
                for part in parts.split('.'):
                    obj = obj.get(part, {})
                if obj == {}:
                    obj = None
            this_issue[field] = obj
        final_results.append(this_issue)

    return final_results


def build_jql_query():
    """Select items from various menus to build a JQL query string"""
    menus = [
        'projects', 'issue types', 'status types', 'query fields', 'date fields',
        'order by fields', 'return fields'
    ]
    selected_menus = ih.make_selections(
        menus,
        prompt='Select the JQL elements you are interested in (separate by space)'
    )
    if not selected_menus:
        return

    s = StringIO()
    # s.write('')
    #
    #
    # - if orderby is used, ask if asc or desc
    #   - if multiple selected, separate by comma
    return s.getvalue()


def get_last_or_make_selection(field_type, force_new=False):
    """Fetch most recent selections for field type from SELECTED_FIELDS

    - field_type: one of the keys in ALLOWED_FIELD_TYPE_INFO dict
    - force_new: if True, prompt user to select fields for field_type
    """
    assert field_type in ALLOWED_FIELD_TYPE_INFO, (
        'field_type {} is not one of {}'.format(
            repr(field_type), repr(sorted(ALLOWED_FIELD_TYPE_INFO.keys()))
        )
    )

    last = None
    selections = None
    if not force_new:
        last = SELECTED_FIELDS.find(
            'type:{}'.format(field_type),
            limit=1,
            get_fields='selected'
        )
        if last:
            selections = last[0]['selected']

    if not selections or force_new:
        selections = ih.make_selections(
            ALLOWED_FIELD_TYPE_INFO[field_type]['fields'],
            prompt=ALLOWED_FIELD_TYPE_INFO[field_type]['prompt']
        )
        if selections:
            SELECTED_FIELDS.add(type=field_type, selected=selections)

    return selections


def choose_old_selection_or_make_new_selection(field_type):
    """Choose from old groups of selections for field_type or make a new selection

    - field_type: one of the keys in ALLOWED_FIELD_TYPE_INFO dict
    """
    assert field_type in ALLOWED_FIELD_TYPE_INFO, (
        'field_type {} is not one of {}'.format(
            repr(field_type), repr(sorted(ALLOWED_FIELD_TYPE_INFO.keys()))
        )
    )

    selections = None
    choice = ih.make_selections(
        ['Choose from old selections', 'Make a new selection'],
        prompt='Choose one for {} fields in search results'.format(field_type),
        unbuffered=True
    )
    if 'Choose from old selections' in choice:
        found = SELECTED_FIELDS.find(
            'type:{}'.format(field_type),
            get_fields='selected,name'
        )

        selected = ih.make_selections(
            found,
            item_format='({name}): {selected}',
            prompt='Choose one',
            wrap=False,
            unbuffered=True
        )
        if selected:
            selections = selected[0]['selected']
            name = selected[0]['name']
            _id = selected[0]['_id']
            update_kwargs = {
                'chosen_on': dh.utc_now_float_string()
            }
            if name is None:
                name = ih.user_input('Enter a name for this selection')
                if name:
                    update_kwargs.update(name=name)
            SELECTED_FIELDS.update(_id, **update_kwargs)
    else:
        selections = get_last_or_make_selection(field_type, force_new=True)

    return selections


chfunc = OrderedDict([
    ('u', (lambda: print(JIRA_API_USER), 'Show API User')),
    ('U', (lambda: print(JIRA_URL), 'Show URL of JIRA server')),
    # ('b', (build_jql_query, 'Build a JQL query')),
])


class JiraREPL(GetCharLoop):
    """A REPL to make calls to JQL search api on HighGround JIRA"""
    def __init__(self, *args, **kwargs):
        self._session = kwargs.pop('session', get_session())
        last_query = SAVED_QUERIES.find(get_fields='jql', limit=1)
        jql = ''
        if last_query:
            jql = last_query[0]['jql']
        self._info = {
            'return_fields': get_last_or_make_selection('return'),
            'orderby_fields': get_last_or_make_selection('orderby'),
            'count_only': False,
            'raw_json': False,
            'last_jql': jql
        }

        super(JiraREPL, self).__init__(*args, **kwargs)

        self._chfunc_dict_update([
            ('j', (self.jql_search, 'Prompt for jql query to make and pass to jql_search')),
            ('J', (self.rerun_last_jql_search, 'Re-run last jql query')),
            ('r', (self.set_return_fields, 'Set return fields for search results')),
            ('o', (self.set_orderby_fields, 'Set order by fields for search results')),
            ('c', (self.toggle_count_only, 'Toggle count-only for search results')),
            ('R', (self.toggle_raw_json, 'Toggle raw JSON for search results')),
            ('i', (self.info, 'Show info about current settings')),
        ])

    def jql_search(self, *args):
        """Submit a JQL search query to the server"""
        jql = None
        if args and args != ('',):
            jql = ' '.join(args)
            SAVED_QUERIES.add(jql=jql)
        else:
            entry_type = ih.make_selections(
                ['Select a saved query', 'Type a JQL query'],
                prompt='Choose one',
                unbuffered=True
            )
            if 'Select a saved query' in entry_type:
                selected_query = ih.make_selections(
                    SAVED_QUERIES.find(get_fields='name,jql'),
                    prompt='Choose one',
                    item_format='({name}) {jql}',
                    unbuffered=True
                )
                if selected_query:
                    jql = selected_query[0]['jql']
                    name = selected_query[0]['name']
                    _id = selected_query[0]['_id']
                    update_kwargs = {
                        'chosen_on': dh.utc_now_float_string()
                    }
                    if name is None:
                        name = ih.user_input('Enter a name for this selection')
                        if name:
                            update_kwargs.update(name=name)
                    SAVED_QUERIES.update(_id, **update_kwargs)
                else:
                    jql = ih.user_input('Enter your JQL query')
                    if not jql:
                        return
                    SAVED_QUERIES.add(jql=jql)
            else:
                jql = ih.user_input('Enter your JQL query')
                if not jql:
                    return
                SAVED_QUERIES.add(jql=jql)

        self._info['last_jql'] = jql

        if not 'order by' in jql.lower() and self._info['orderby_fields']:
            jql += ' ORDER BY ' + ', '.join(self._info['orderby_fields'])

        results = jql_search(
            jql,
            session=self._session,
            count=self._info['count_only'],
            fields=self._info['return_fields'],
            return_raw=self._info['raw_json']
        )
        pprint(results)
        print('\njql:', jql)

    def rerun_last_jql_search(self, *args):
        """Re-run last jql query"""
        last = SAVED_QUERIES.find(get_fields='jql', limit=1)
        jql = ''
        if last:
            jql = last[0]['jql']
        self.jql_search(jql)

    def set_return_fields(self, *args):
        """Set return fields for search results"""
        selection = choose_old_selection_or_make_new_selection('return')
        if selection:
            self._info['return_fields'] = selection

    def set_orderby_fields(self, *args):
        """Set order by fields for search results"""
        selection = choose_old_selection_or_make_new_selection('orderby')
        if selection:
            self._info['orderby_fields'] = selection

    def toggle_count_only(self, *args):
        """Toggle count-only for search results"""
        self._info['count_only'] = not self._info['count_only']

    def toggle_raw_json(self, *args):
        """Toggle raw JSON for search results"""
        self._info['raw_json'] = not self._info['raw_json']

    def info(self, *args):
        """Show info about current settings"""
        pprint(self._info)


def get_repl():
    """Return an instance of JiraREPL"""
    return JiraREPL(chfunc_dict=chfunc, name='jira', prompt='jira-repl> ')

