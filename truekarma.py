from __future__ import absolute_import, division, print_function, unicode_literals

from ConfigParser import SafeConfigParser
from collections import OrderedDict
from datetime import datetime
from imgurpython import ImgurClient
from PIL import Image
from praw.handlers import MultiprocessHandler
import logger
import matplotlib.pyplot as plt
import numpy as np
import os
import pandas as pd
import praw
import re
import seaborn as sns
import tempfile
import time
import threading


def accumu(lis):
    total = 0
    for x in lis:
        if np.isnan(x):
            x = 0
        total += x
        yield total


def get_user_ts(user_name):
    thing_limit = None
    user = r.get_redditor(user_name)
    sub_gen = user.get_submitted(limit=thing_limit)
    subs = [s for s in sub_gen]
    sub_dt = [datetime.utcfromtimestamp(s.created_utc) for s in subs][::-1]
    sub_score = [s.score for s in subs][::-1]
    com_gen = user.get_comments(limit=thing_limit)
    coms = [c for c in com_gen]
    com_dt = [datetime.utcfromtimestamp(c.created_utc) for c in coms][::-1]
    com_score = [c.score for c in coms][::-1]
    
    ts = pd.DataFrame({'sub' : pd.Series(sub_score, index=sub_dt),
                       'com' : pd.Series(com_score, index=com_dt)})
    ts['sub_cum'] = [v for v in accumu(ts['sub'])]
    ts['com_cum'] = [v for v in accumu(ts['com'])]
    ts['tot_cum'] = ts['sub_cum']+ts['com_cum']
    
    return ts


def gen_image(ts, user_name):
    cmap = sns.color_palette("Dark2", 3)
    fig, (ax1, ax3) = plt.subplots(1, 2, figsize=(14, 6), dpi=80)
    ts['sub_cum'].plot(color=cmap[0], ax=ax1, label='Submissions')
    ax1.axhline(0, color=cmap[0], linestyle='--')
    ax1.set_ylabel('Submission Karma', color=cmap[0])
    for tl in ax1.get_yticklabels():
        tl.set_color(cmap[0])

    ax2 = ax1.twinx()
    ts['com_cum'].plot(color=cmap[1], ax=ax2, label='Comments')
    ax2.axhline(0, color=cmap[1], linestyle='--')
    ax2.set_ylabel('Comment Karma', color=cmap[1])
    for tl in ax2.get_yticklabels():
        tl.set_color(cmap[1])

    ax2.set_yticks(np.linspace(ax2.get_yticks()[0], ax2.get_yticks()[-1], len(ax1.get_yticks())))
    ax2.grid(False)
    ax1.set_title('Submission/Comment Karma')

    ts['sub_cum'].plot(color=cmap[0], ax=ax3, label='Submissions')
    ts['com_cum'].plot(color=cmap[1], ax=ax3, label='Comments')
    ts['tot_cum'].plot(color=cmap[2], ax=ax3, label='Total')
    ax3.axhline(0, color='k', linestyle='--')
    ax3.legend(frameon=True, loc=2).get_frame().set_color([1, 1, 1, 0.5])
    ax3.set_ylabel('Karma')
    ax3.set_title('All Karma')

    plt.subplots_adjust(wspace=0.5)
    plt.suptitle('Cumulative TrueKarma for /u/{0} (S:{1} + C:{2} = T:{3})'.format(
                  user_name,
                  int(ts['sub_cum'].tail(1)),
                  int(ts['com_cum'].tail(1)),
                  int(ts['tot_cum'].tail(1))),
                 fontsize=14, fontweight='bold')
    
    return fig


def keyword_search(session, username_queue, run_event):
    keyword = u'truekarma /u/'
    for comment in praw.helpers.comment_stream(session, 'all', verbosity=0, limit=None):
        if run_event.is_set():
            commentbody = comment.body.lower()
            if keyword in commentbody:
                valid_name = re.compile(r'[T,t]rue[K,k]arma \/u\/([\w-]+)', re.UNICODE)
                user_name = valid_name.findall(commentbody)[0]
                if user_name not in username_queue.keys():
                    username_queue[user_name] = comment
                    log.info('Added {0} to queue, queue length = {1}'.format(user_name, len(username_queue)))
            time.sleep(0.0001)
        else:
            break


def process_username(session, username_queue, run_event):
    while (True):
        if run_event.is_set():
            if username_queue:
                [user_name, comment] = username_queue.popitem(last=True)
                log.info('Processing {0}'.format(user_name))
                try:
                    ts = get_user_ts(user_name)
                    img_fig = gen_image(ts, user_name)
                    log.info('Processed {0}'.format(user_name))
                except TypeError:
                    log.info('No user data')
                    continue
                except praw.errors.NotFound as error:
                    log.info('{0} not found'.format(user_name))
                    continue
                # Save to temporary file and upload
                temp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                log.debug('Temporary file name: {0}'.format(temp.name))
                img_fig.savefig(temp.name, format='png', dpi=600)
                temp.close()
                try:
                    uploaded_image = im.upload_from_path(temp.name, config={'title':'Cumulative TrueKarma for /u/{0}'.format(user_name)})
                    log.debug('Uploaded to {0}'.format(uploaded_image['link']))
                except:
                    raise
                finally:
                    os.remove(temp.name)
                try:
                    comment.reply('TrueKarma for /u/{user}:\n\n'
                        '  * Submissions: {sub}\n'
                        '  * Comments: {com}\n'
                        '  * Total: {tot}\n'
                        '  * [Historical Graph]({link})\n\n'
                        '*****\n'
                        '^(TrueKarma bot, summon with "TrueKarma /u)^\/UserName"'
                        ' '.format(user=user_name,
                                   sub=int(ts['sub_cum'].tail(1)),
                                   com=int(ts['com_cum'].tail(1)),
                                   tot=int(ts['tot_cum'].tail(1)),
                                   link=uploaded_image['link']))
                except praw.errors.RateLimitExceeded as error:
                    log.warning('Hit rate limit... sleeping for {0} seconds'.format(error.sleep_time))
                    time.sleep(error.sleep_time)
                    continue
                log.debug('Posted reply')
            time.sleep(0.1)
        else:
            break

config = SafeConfigParser()
config.read('config.ini')
handler = MultiprocessHandler()
r = praw.Reddit(user_agent=config.get('reddit', 'user_agent'),
                workonhandler=handler)
r.login(config.get('reddit', 'username'),
        config.get('reddit', 'password'), disable_warning=True)
im = ImgurClient(config.get('imgur', 'client_id'),
                 config.get('imgur', 'client_secret'))
log = logger.logger('truekarma', logger.DEBUG)

def main():
    # Setup the threading event
    run_event = threading.Event()
    run_event.set()
    # Thread #1 Comment scanner
    log.info('Starting comment scanner')
    username_queue = OrderedDict()
    t1 = threading.Thread(target=keyword_search,
                          args=(r, username_queue, run_event))
    t1.start()
    # Thread #2 Username processor
    log.info('Starting username processor')
    t2 = threading.Thread(target=process_username,
                          args=(r, username_queue, run_event))
    t2.start()

    try:
        while (True):
            time.sleep(0.1)
    except:
        log.warning("Attempting to close threads...")
        run_event.clear()
        t1.join()
        t2.join()
        log.warning("Threads successfully closed...")
        raise
        
if __name__ == '__main__':
    main()