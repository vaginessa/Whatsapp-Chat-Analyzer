import re
import json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from src import db_handler as db

RE_EMOJI = '<(?:Emoji)(?:[^>]+)>'
RE_MEDIA = '<(?:Media)(?:[^>]+)>'
RE_LINK = '(?:(?:(?:https|http|ftp):\/\/(?:www\.)?)|(?:www\.))\S+\.\S+'
RE_MENTION = '@\d+'
RE_LOCATION = f'(?:live location shared|(?:location:\s{RE_LINK}))'
RE_CONTACT = '^.+\.(vcf \(file attached\))'
RE_EVENTS = [
    '^(Messages to this group are now secured with end-to-end encryption.)\s.+',
    '(.+)\s(created group)\s.+',
    '(.+)\s(changed the subject)\s.+',
    "(.+)\s(changed this group's icon)",
    '(.+)\s(added)\s(.+)',
    '(.+)\s(changed their phone number)\s.+',
    '(.+)\s(changed to)\s(.+)',
    '(.+)\s(left)'
]

def replace_emoji(text, emoji):
    """Convert unicode character of emoji into string representation."""
    new_text = text
    for idx, emo in filter(lambda x: x[1] in text, emoji):
        new_text = new_text.replace(emo, f'<Emoji_{idx}>')
    for i in re.findall('(\\\\ufe0.|\\\\u206[89])', new_text):
        new_text = new_text.replace(i, '')
    return new_text

def detect_pattern():
    """Return python date-format pattern from first line of chat."""
    return '%m/%d/%y, %H:%M - '

def convert_to_re_pattern(pattern):
    """Convert python date-format pattern into regular expression pattern."""
    symb_conv = lambda x: '\d{1,' + str(len(datetime.today().strftime(x))) + '}'
    re_pattern = ''
    i = 0
    while i < len(pattern):
        if pattern[i] == '%':
            re_pattern += symb_conv(pattern[i:i+2])
            i += 1
        elif pattern[i] in '/()[].$^*?':
            re_pattern += '\\' + pattern[i]
        else:
            re_pattern += pattern[i]
        i += 1
    return re_pattern

def clean_message(text):
    """Remove newline, emoji, and media from message."""
    text = text.replace('\n', ' ')
    text = re.sub(RE_LOCATION, '', text)
    text = re.sub(RE_EMOJI, '', text)
    text = re.sub(RE_MEDIA, '', text)
    text = re.sub(RE_LINK, '', text)
    text = re.sub(RE_MENTION, '', text)
    text = re.sub(RE_CONTACT, '', text)
    return text

def find_link(text):
    """Find links from message."""
    list_link = []
    if len(re.findall(RE_LOCATION, text)) == 0:
        for link in re.findall(RE_LINK, text):
            if link[-1] in ['.', ',']:
                temp = link[:-1]
            else:
                temp = link
            list_link.append(temp)
    return list_link

def get_category(x):
    contact, message = x
    if contact == '':
        return 'Event'
    elif re.match(RE_MEDIA, message):
        return 'Media'
    elif re.match(RE_LOCATION, message):
        return 'Location'
    elif re.match(RE_CONTACT, message):
        return 'Contact'
    else:
        return 'Message'

def extract_event(text):
    for event in RE_EVENTS:
        match = re.match(event, text)
        if match:
            matchs = match.groups()
            if len(matchs) == 3:
                contact, message, contact2 = matchs
            elif len(matchs) == 2:
                contact, message, contact2 = matchs[0], matchs[1], ''
            else:
                contact, message, contact2 = '', matchs[0], ''
            return contact, message, contact2
    return '', text, ''

def enrich(df):
    """Adding some column for analysis."""
    df['clean_message'] = df.message.apply(clean_message)
    df['date'] = df.datetime.dt.date
    df['year'] = df.date + pd.offsets.YearEnd(0)
    df['month'] = df.date + pd.offsets.MonthEnd(0)
    df['week'] = df.date + pd.offsets.Week(weekday=6)
    df['day'] = pd.Categorical(df.datetime.dt.strftime('%A'))
    df['hour'] = pd.Categorical(df.datetime.apply(lambda x: x.strftime('%H:00')))
    df['list_emoji'] = df.message.apply(lambda x: re.findall(RE_EMOJI, x))
    df['list_link'] = df.message.apply(find_link)
    df['list_mention'] = df.message.apply(lambda x: re.findall(RE_MENTION, x))
    df['list_words'] = df.clean_message.apply(lambda x: re.findall('\w+', x))
    df['count_emoji'] = df.list_emoji.apply(len)
    df['count_link'] = df.list_link.apply(len)
    df['count_mention'] = df.list_mention.apply(len)
    df['count_words'] = df.list_words.apply(len)
    df['count_character'] = df.clean_message.apply(len)
    df['count_newline'] = df.message.str.count('\n')
    df['category'] = df[['contact', 'message']].apply(get_category, axis=1)
    df['is_message'] = df.category == 'Message'
    df['contact2'] = np.nan
    df.loc[df.category == 'Event', 'contact'], df.loc[df.category == 'Event', 'message'], df.loc[df.category == 'Event', 'contact2'], = zip(*df[df.category == 'Event'].message.apply(extract_event))
    return df

def parse(chat, save=True):
    """Parse exported chat and define date, contact, message for each message."""
    pattern = detect_pattern()
    re_pattern = convert_to_re_pattern(pattern)
    emoji = db.get_emoji()[['index', 'unicode']].values.tolist()

    chat = chat.decode().encode('unicode_escape').decode('utf-8')
    dates = re.findall(re_pattern, chat)
    msgs = re.split(re_pattern, chat)
    msgs.pop(0)

    data = []
    for date, msg in zip(dates, msgs):
        date = datetime.strptime(date, pattern)
        msg_splitted = msg.split(': ', 1)
        if len(msg_splitted) > 1:
            contact, msg = msg_splitted
        else:
            contact, msg = '', msg_splitted[0]
        if '\\U000' in msg or '\\u' in msg:
            msg = replace_emoji(msg, emoji)
        if msg[-2:] == '\\n':
            msg = msg[:-2]
        data.append({
            'datetime': date,
            'contact': contact,
            'message': msg.encode().decode('unicode_escape')})
    df = pd.DataFrame(data)
    return df

def load_parsed_data(input_string, input_type, save=True):
    if input_type == 'upload':
        df = parse(input_string, save)
        url = db.generate_url(10)
        if save:
            db.reset_chat() # TODO: delete this for production
            url = db.add_chat(df, url)
    elif input_type == 'url':
        url = input_string
        df = db.get_chat(url)
    if df.empty:
        return 'not_found', {'data': ''}
    df = enrich(df)
    # TODO: support for both private & group chat
    group_created = df[(df.category == 'Event') & (df.message == 'created group')]
    df = df.drop(group_created.index)
    group_created = [group_created['contact'], group_created['datetime']]
    users = sorted(filter(lambda x: len(x) > 0, df.contact.unique().tolist()))
    df = df.drop(['message', 'clean_message'], axis=1)
    datasets = {
        'data': df.to_json(date_format='iso', orient='split'),
        'users': users
    }
    return '/groupchat/' + url, json.dumps(datasets)