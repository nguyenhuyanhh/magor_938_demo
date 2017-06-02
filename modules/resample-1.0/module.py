"""
Module: resample
Version: 1.0
Author: Nguyen Huy Anh

Requires:

Resample a file_id into /resample
"""

import logging
import os
import sys

from ffmpy import FFmpeg

CUR_DIR = os.path.dirname(os.path.realpath(__file__))
ROOT_DIR = os.path.dirname(os.path.dirname(CUR_DIR))
DATA_DIR = os.path.join(ROOT_DIR, 'data/')

MODULE_NAME = 'resample'
LOG_H = logging.StreamHandler()
LOG_F = logging.Formatter(
    '%(asctime)s (%(name)s | %(levelname)s) : %(message)s')
LOG_H.setFormatter(LOG_F)
LOG = logging.getLogger(MODULE_NAME)
LOG.propagate = False
LOG.addHandler(LOG_H)
LOG.setLevel(logging.DEBUG)


def resample(file_id):
    """Resample a file_id."""
    # init paths
    working_dir = os.path.join(DATA_DIR, file_id)
    raw_dir = os.path.join(working_dir, 'raw/')
    resample_dir = os.path.join(working_dir, 'resample/')

    # resample
    audio_in = os.path.join(raw_dir, os.listdir(raw_dir)[0])
    audio_out = os.path.join(resample_dir, '{}.wav'.format(file_id))
    if os.path.exists(audio_out) and os.path.getsize(audio_out) > 0:
        LOG.debug('Previously resampled %s', audio_out)
    else:
        if not os.path.exists(resample_dir):
            os.makedirs(resample_dir)
        inputs = {audio_in: None}
        outputs = {audio_out: '-ac 1 -ar 16000 -sample_fmt s16'}
        ffmp = FFmpeg(inputs=inputs, outputs=outputs)
        LOG.debug('Resampling command: %s', ffmp.cmd)
        fnull = open(os.devnull, 'w')
        ffmp.run(stdout=fnull, stderr=fnull)  # silent output
        LOG.debug('Resampled %s to %s', audio_in, audio_out)

if __name__ == '__main__':
    resample(sys.argv[1])
