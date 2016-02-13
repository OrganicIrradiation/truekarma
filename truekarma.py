from collections import OrderedDict
from datetime import datetime
from imgurpython import ImgurClient
from praw.handlers import MultiprocessHandler
import configparser
import logger
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import OAuth2Util
import os
import pandas as pd
import praw
import re
import seaborn as sns
import tempfile
import time


def accumu(lis):
    total = 0
    for x in lis:
        if np.isnan(x):
            x = 0
        total += x
        yield total


def get_user_ts(session, username):
    thing_limit = None
    user = r.get_redditor(username)
    sub_gen = user.get_submitted(limit=thing_limit)
    subs = [s for s in sub_gen]
    sub_dt = [datetime.utcfromtimestamp(s.created_utc) for s in subs][::-1]
    sub_score = [s.score for s in subs][::-1]
    com_gen = user.get_comments(limit=thing_limit)
    coms = [c for c in com_gen]
    com_dt = [datetime.utcfromtimestamp(c.created_utc) for c in coms][::-1]
    com_score = [c.score for c in coms][::-1]

    sub_df = pd.DataFrame(sub_score, columns=['sub'], index=sub_dt)
    com_df = pd.DataFrame(com_score, columns=['com'], index=com_dt)
    sub_df.drop_duplicates(inplace=True)
    com_df.drop_duplicates(inplace=True)
    ts = pd.concat([sub_df, com_df], axis=1)
    
    ts['sub_cum'] = [v for v in accumu(ts['sub'])]
    ts['com_cum'] = [v for v in accumu(ts['com'])]
    ts['tot_cum'] = ts['sub_cum']+ts['com_cum']

    return ts


def gen_image(ts, username):
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

    ax2.set_yticks(np.linspace(ax2.get_yticks()[0],
                               ax2.get_yticks()[-1],
                               len(ax1.get_yticks())))
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
    plt.suptitle('/u/{0}\'s True Karma (S:{1} + C:{2} = T:{3})'.format(
                username,
                int(ts['sub_cum'].tail(1)),
                int(ts['com_cum'].tail(1)),
                int(ts['tot_cum'].tail(1))),
                fontsize=14, fontweight='bold')
    plt.setp( ax1.xaxis.get_majorticklabels(), rotation=30 )
    plt.setp( ax3.xaxis.get_majorticklabels(), rotation=30 )

    return fig


def process_message(session, message_queue):
    [username, message] = list(message_queue.items())[0]
    log.info('Processing /u/{0}'.format(username))
    try:
        ts = get_user_ts(session, username)
        log.debug('Processed time series')
    except TypeError:
        log.info('No user data')
        return False
    except praw.errors.InvalidUser:
        log.info('/u/{0} does not exist'.format(username))
        return False
    except praw.errors.NotFound:
        log.info('/u/{0} not found'.format(username))
        return False

    # Save to temporary file and upload
    try:
        img_fig = gen_image(ts, username)
    except TypeError:
        log.info('/u/{0} history is empty'.format(username))
        return False
    temp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
    img_fig.savefig(temp.name, format='png', dpi=600)
    temp.close()
    log.debug('Image generated, temp file name: {0}'.format(temp.name))
    try:
        uploaded_image = im.upload_from_path(temp.name, config={'title': 'Cumulative True Karma for /u/{0}'.format(username)})
        log.debug('Uploaded to {0}'.format(uploaded_image['link']))
    except:
        raise
    finally:
        os.remove(temp.name)
    try:
        message.reply('True Karma for /u\/{user}:\n\n'
                      '  * Submissions: {sub}\n'
                      '  * Comments: {com}\n'
                      '  * Total: {tot}\n'
                      '  * [Historical Graph]({link})\n\n'
                      '*****\n'
                      '^(True Karma bot, summon with "+/u)^\/True-Karma ^UserName"'
                      ''.format(user=username,
                                sub=int(ts['sub_cum'].tail(1)),
                                com=int(ts['com_cum'].tail(1)),
                                tot=int(ts['tot_cum'].tail(1)),
                                link=uploaded_image['link']))
        log.debug('Posted reply')
    except praw.errors.RateLimitExceeded:
        raise
    except APIException as error:
        if str(error) == "(DELETED_COMMENT) `that comment has been deleted` on field `parent`":
            log.warning('Comment was deleted before reply')
            pass
        else:
            raise
    return True


config = configparser.ConfigParser()
config.read('config.ini')

r = praw.Reddit(config.get('reddit', 'user_agent'))
o = OAuth2Util.OAuth2Util(r)
o.refresh(force=True)

im = ImgurClient(config.get('imgur', 'client_id'),
                 config.get('imgur', 'client_secret'))
log = logger.logger('truekarma', logger.DEBUG)
message_queue = OrderedDict()
valid_name = re.compile(r'\+\/u\/[T,t]rue\-[K,k]arma ([\w-]+)', re.UNICODE)


def main():
    log.info('Main loop running')
    running = True
    while running:
        try:
            messages = r.get_unread()

            for m in messages:
                try:
                    for username in valid_name.findall(m.body)[:5]:
                        if username not in message_queue.keys():
                            message_queue[username] = m
                            log.info('Added /u/{0} to queue, queue length = {1}'.format(username, len(message_queue)))
                        else:
                            log.debug('/u/{0} already in queue.'.format(username))
                except:
                    log.debug('Invalid summon command, username problem')
                    pass

            if message_queue:
                success = process_message(r, message_queue)
                [_, message] = list(message_queue.items())[0]
                message.mark_as_read()
                message_queue.popitem(last=False)

        except KeyboardInterrupt:
            log.warning("Received KeyboardInterrupt, shutting down...")
            running = False
        except praw.errors.RateLimitExceeded as error:
            log.warning('Rate limit exceeded, sleeping for {0} seconds...'.format(error.sleep_time))
            time.sleep(error.sleep_time)
            continue
        # except Exception as error:
        #     log.error('Unhandled error: {0}'.format(error))
        #     log.warning('Sleeping for {0} seconds...'.format(60))
        #     time.sleep(60)
        #     continue

        time.sleep(15)


if __name__ == '__main__':
    main()
