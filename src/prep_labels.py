# Script for preparing training labels
# Author: Nick Wilkinson 2021
import argparse
import numpy as np
import pandas as pd
import os
import utils


def get_labels(data: pd.DataFrame, frame_length: float = 0.32, rate: int = 16000) -> pd.DataFrame:
    '''Function for preparing training labels.

    Args:
        data: A pd.DataFrame containing datatset information and signals -- see docs for prep_data().
        frame_length (optional): Length of a spectrogram feature in seconds. Default is 0.32.
        rate (optional): Sample rate. Default is 16k.

    Returns:
        A pd.DataFrame containing labels and metadata.
    '''

    data['labels'] = data.apply(lambda x: _generate_label_sequence(x, frame_length, rate), axis=1)
    data = data.drop(['signal', 'label'], axis=1)
    data = data.dropna().reset_index(drop=True)
    return data


def one_hot(col: pd.Series) -> pd.Series:
    '''Function for converting string labels to one-hot encoded labels. One-hot mapping is done
    in alphabetical order of sting labels eg. {a: [1, 0, 0], b = [0, 1, 0], c = [0, 0, 1]}.

    Args:
        col: A column of a pd.DataFrame containing label sequences generated by get_labels().

    Returns:
        A pd.Series containing the label sequences conveted to one-hot encoding.
    '''

    unique = np.unique(np.hstack(col))
    label_map = {}
    for n, i in enumerate(unique):
        temp = np.zeros(len(unique))
        temp[n] = 1
        label_map[i] = temp
    return col.apply(lambda x: np.array([label_map[i] for i in x]))


def prep_data(path: str) -> pd.DataFrame:
    '''Function for creating pd.DataFrame containing dataset information specified by Kaldi-style
    data directory containing 'wav.spc', 'segments' and 'utt2spk'.

    Args:
        data_dir: The path to the data directory.

    Returns:
        A pd.DataFrame of dataset information. For example:

            recording-id  extended filename        utterance-id  start  end  label       signal
        0   rec_00        ~/Documents/test_00.wav  utt_00        10     20   speech      [-49, -43, -35...
        1   rec_00        ~/Documents/test_00.wav  utt_01        50     60   non_speech  [-35, -23, -12...
        2   rec_01        ~/Documents/test_01.wav  utt_02        135    163  speech      [25, 32, 54...
    '''

    wav_scp, segments, utt2spk = utils.process_data_dir(path)
    assert utt2spk is not None and segments is not None, \
        'ERROR: Data directory needs to contain \'segments\' and \'utt2spk\'\
            containing label information.'
    data = wav_scp.merge(segments).merge(utt2spk)
    data = data.rename(columns={"speaker-id": "label"})
    data = data.merge(utils.read_sigs(data))
    return data


def _generate_label_sequence(row: pd.DataFrame, frame_length: float, rate: int) -> np.ndarray:
    '''Auxiliary function used by get_labels(). Generated label arrays from a row of a pd.DataFrame
    containing dataset information created by prep_data().

    Args:
        frame_length: Length of a spectrogram feature in seconds.
        rate: Sample rate.

    Returns:
        An np.ndarray of labels.
    '''

    sig = row['signal']
    if 'utterance-id' in row:
        id = row['utterance-id']
    else:
        id = row['recording-id']
    try:
        assert len(range(0, int(len(sig)-1 - (frame_length+0.01) * rate), int(frame_length * rate))) > 0
        labels = []
        for _ in utils.progressbar(range(0, int(len(sig)-1 - (frame_length+0.01) * rate), int(frame_length * rate)), id):
            labels.append(row['label'])
        return np.array(labels)
    except AssertionError:
        pass

# Handle args when run directly
if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='prep_labels',
                                     description='Prepare labels for model training.')

    parser.add_argument('data_dir', type=str,
                        help='a path to a Kaldi-style data directory containting \'wav.scp\', \'segments\', and \'utt2spk\'')
    
    parser.add_argument('out_dir', type=str,
                        help='a path to an output directory where labels and metadata will be saved as labels.h5')

    args = parser.parse_args()
    data = prep_data(args.data_dir)
    labels = get_labels(data)
    labels['labels'] = one_hot(labels['labels'])
    if not os.path.exists(args.out_dir):
        print(f'Directory {args.out_dir} does not exist, creating it.')
        os.mkdir(args.out_dir)
    utils.save(labels, f'{args.out_dir}/labels.h5')