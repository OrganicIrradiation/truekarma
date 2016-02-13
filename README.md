# truekarma

This is a [Reddit](http://reddit.com) bot that calculates a user's "true karma" from their individual submissions and comments. On Reddit, a user's karma score (which is a representation of upvotes for their submitted content) weights up and downvotes differentially. This means that some users who receive a large number of downvotes can still have a positive karma score.

This bot:

 1. Continuously searches the Reddit comment stream for the summoning phrase "+/u/True-Karma UserName"
 2. Searches through the /u/UserName's history
 3. Calculates the cumulative scores for their past 1000 submissions and 1000 comments
 4. Generates a small graphic and uploads it to imgur
 5. Responds to the summoning phrase with the statistics and graphic

Note that the generation of the submission/comment score may take some time, so there can be a delay if there is a queue for submissions.

## Setup

This bot uses [OAuth2Util](https://github.com/SmBe19/praw-OAuth2Util) to handle most of the dirty work with logging in, so there is a little bit of setup required.

 1. Go to https://www.reddit.com/prefs/apps/ and create an app. It should preferably be a script and the ```redirect uri``` should point to ```http://127.0.0.1:65010/authorize_callback```.
 2. Create an oauth.ini file. An example is provided in example_oauth.ini. The main things are the the scope needs to include "privatemessages,read,submit,history" and you need to make sure to include your app_key and app_secret.

The bot also uses imgurpython to post the analysis image to imgur.com. You will need to create a config.ini file with your client_id and client_secret. An example is provided in example_config.ini