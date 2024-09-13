import feedparser
import os.path
import json
import requests
import html2text
import re
import configparser

feedLastUpdatedJsonPath = 'RSS-notifier-last-updated.json'
RSSlist = ['https://pubmed.ncbi.nlm.nih.gov/rss/journals/101532453/?limit=10&name=Insights%20Imaging&utm_campaign=journals',
           'https://pubmed.ncbi.nlm.nih.gov/rss/journals/101674571/?limit=10&name=Abdom%20Radiol%20%28NY%29&utm_campaign=journals',
           'https://pubmed.ncbi.nlm.nih.gov/rss/journals/8302501/?limit=20&name=Radiographics&utm_campaign=journals',
           'https://pubmed.ncbi.nlm.nih.gov/rss/journals/7708173/?limit=15&name=AJR%20Am%20J%20Roentgenol&utm_campaign=journals',
           'https://pubmed.ncbi.nlm.nih.gov/rss/journals/9114774/?limit=10&name=Eur%20Radiol&utm_campaign=journals']
# Telegram BOT Token
telegramBotToken = ''

receivers = []

whitelists_by_category = {'uro': ['urogenital' 'genitourina', 'urinary'
                                  'renal', 'kidney', 'bladder', 'vesical', 'urothelial',
                                  'prostat', 'seminal', 'penis', 'testic', 'scrotum', 'scrotal'],
                          'abdomen': ['abdomen', 'abdominal',
                                      'peritoneum', 'peritoneal', 'perineal', 'perineum',
                                      ' liver', 'hepatic', 'hepato', 'biliar', 'gallbladder',
                                      'pancrea', 'spleen', 'splenic',
                                      'gastro', 'gastric', 'duoden', 'jejun', 'ileum', 'ileal',
                                      'colon', 'sigmoid', 'rectum', 'rectal', 'anus', ' anal ',
                                      'uterus', 'uterine', 'ovary', 'ovarian', 'adnex', 'cervix', 'vagina']}
blacklist = ['Letter to the Editor', 'Erratum for: ']


# Retrieves RSS list, and sends new ones to phone
def main(RSSlist = RSSlist):
    lastUpdatedMetadata = {}
    if os.path.isfile(feedLastUpdatedJsonPath):
        with open(feedLastUpdatedJsonPath) as f:
            lastUpdatedMetadata = json.load(f)
    feeds = []
    for link in RSSlist:
        # Check if we already have downloaded it once
        feed = feedparser.parse(link)
        if link in lastUpdatedMetadata.keys():
            if lastUpdatedMetadata[link]['last_published'] == feed.feed.published:
                print('{} has not changed, don\'t push to phone'.format(lastUpdatedMetadata[link]['feed_title']))
            else:
                print('{} has changed, looking for new entries:'.format(lastUpdatedMetadata[link]['feed_title']))
                send_new_entries(feed, lastUpdatedMetadata[link]['last_entry_doi'])
        else:
            print('New feed added: {}.'.format(feed['feed']['title']))
        feeds.append(feed)
    save_last_modified(feeds)

def save_last_modified(feeds):
    lastUpdatedMetadata = {}
    for feed in feeds:
        feed_title = feed.feed.title
        feed_link = feed.feed.subtitle_detail.base
        last_published = feed.feed.published
        last_entry_doi = feed['entries'][0]['dc_identifier']
        lastUpdatedMetadata[feed_link] = {'feed_title':     feed_title,
                                          'last_published': last_published,
                                          'last_entry_doi': last_entry_doi}
        with open(feedLastUpdatedJsonPath, 'w', encoding='utf-8') as f:
            json.dump(lastUpdatedMetadata, f, ensure_ascii=False, indent=4)


def send_new_entries(feed, last_entry_doi):
    for entry in feed['entries']:
        if entry['dc_identifier'] == last_entry_doi:
            break
        send_entry_to_telegram_users(entry)

def send_entry_to_telegram_users(entry):
    message = format_entry_for_telegram(entry)
    for person in receivers:
        for whitelist in person['whitelists']:
            if message_passes_whitelist(whitelist, message):
                if message_passes_blacklist(message):
                    send_message_to_telegram(message, person['telegramChatID'])
                    print('Sent entry: {}'.format(entry['title']))
                    break # break out of innermost loop only, so it is send only once!
                else:
                    print('Message {} contains blacklisted word'.format(entry['title']))
            else:
                print('Failed keyword test {} for {}: {}.'.format(whitelist, person['name'], entry['title']))

def message_passes_whitelist(whitelist_category: str, message: str) -> bool:
    for keyword in whitelists_by_category[whitelist_category]:
        if keyword in message:
            return True
    return False

def message_passes_blacklist(message: str) -> bool:
    for keyword in blacklist:
        if keyword in message:
            return False
    return True

def format_entry_for_telegram(entry):
    components = {'title': format_title(entry['title']),
                  'journal': entry['dc_source'],
                  'doi': entry['dc_identifier'][4:],
                  'PMID': entry['id'][7:],
                  'abstract': format_content(entry['content'][0]['value'])}
    return '[{}](https://doi.org/{})'\
        '\n_{}_\n\n{}\n'\
        '[Link](https://doi.org/{}) | '\
        '[Pubmed](https://pubmed.ncbi.nlm.nih.gov/{}/) | '\
        '[QxMD](https://qxmd.com/r/{})'.format(components['title'],
                                               components['doi'],
                                               components['journal'],
                                               components['abstract'],
                                               components['doi'],
                                               components['PMID'],
                                               components['PMID'])

def format_title(title: str) -> str:
    title = html2text.html2text(title)
    title = re.sub(r'[\[\]]', '', title)
    title = re.sub(r'\n+$', '', title)
    return title.replace('\n', ' ')

def format_content(content: str) -> str:
    content = html2text.html2text(content)
    content = content.replace("**", "*") # fix
    content = re.sub(r'(\w[),:\w])\n(\(?\w)', #fix newlines
                     r'\1 \2',
                     content)
    # removes too many newlines in certain places when wordwith-\nhyphen
    content = re.sub(r'(\w-)\n(\w)', r'\1\2', content)
    abstrStart = content.rfind('*ABSTRACT*\n')
    PMIDStart = content.rfind('\n\nPMID:')
    if (abstrStart != -1 and PMIDStart != -1):
        content = content[abstrStart + 12 : PMIDStart]
    elif content.rfind('\n*NO ABSTRACT*\n') != -1:
        content = 'No abstract.'
    # If eg "KEY POINTS:"  occurs in the middle of the text, add some new lines before it
    content = re.sub(r'\. ([A-Z ]{7,}: )', r'.\n\n\1', content)
    return content

def send_message_to_telegram(message, telegramChatID, format="Markdown", disable_web_preview=True):
    data = {
        "chat_id": telegramChatID,
        "text": message,
        "parse_mode": format,
        "disable_web_page_preview": disable_web_preview,
    }
    r = requests.post(f'https://api.telegram.org/bot{telegramBotToken}/sendMessage', data=data)
    print(f'Sent to telegram; respons {r}')

def load_config(configfile = 'config.ini'):
    if not os.path.exists(configfile):
        raise SystemExit('The config.ini file is not found! Make sure you create it according to the readme.')
    config = configparser.ConfigParser()
    config.read(configfile)
    global telegramBotToken
    telegramBotToken = config['DEFAULT']['telegramBotToken']
    for receiver in config:
        if receiver != 'DEFAULT':
            receivers.append({'name': receiver,
                             'telegramChatID': int(config[receiver]['telegramChatID']),
                             'whitelists': format_whitelist_from_config(config[receiver]['whitelists'])})

def format_whitelist_from_config(whitelistString: str) -> list[str]:
    return whitelistString.lower().replace(' ', '').split(',')

if __name__ == "__main__":
    feedLastUpdatedJsonPath = os.path.join(os.path.dirname(__file__), 'RSS-notifier-last-updated.json')
    load_config(os.path.join(os.path.dirname(__file__), 'config.ini'))
    main()
