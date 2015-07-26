truekarma
==========================

This is a [Reddit](http://reddit.com) bot that calculates a user's "true karma" from their individual submissions and comments. On Reddit, a user's karma score (which is a representation of upvotes for their submitted content) weights up and downvotes differentially. This means that some users who receive a large number of downvotes can still have a positive karma score.

This bot:

  # Continuously searches the Reddit comment stream for the summoning phrase "TrueKarma /u/UserName"
  # Searches through the /u/UserName's history
  # Calculates the cumulative scores for their submissions and comments
  # Generates a small graphic
  # Responds to the summoning phrase

Note that the generation of the submission/comment score may take some time, so there can be a delay if there is a queue for submissions.