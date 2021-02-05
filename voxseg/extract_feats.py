# Module for extracting log-mel spectrogram features,
# may also be run directly as a script
# Author: Nick Wilkinson 2021
import argparse
import numpy as np
import pandas as pd
import os
from voxseg import utils
from python_speech_features import logfbank


def extract(data: pd.DataFrame, frame_length: float = 0.32, nfilt: int = 32, rate: int = 16000) -> pd.DataFrame:
    '''Function for extracting log-mel filterbank spectrogram features.

    Args:
        data: A pd.DataFrame containing datatset information and signals -- see docs for prep_data().
        frame_length (optional): Length of a spectrogram feature in seconds. Default is 0.32.
        nfilt (optional): Number of filterbanks to use. Default is 32.
        rate (optional): Sample rate. Default is 16k.

    Returns:
        A pd.DataFrame containing features and metadata.
    '''
    
    print('--------------- Extracting features ---------------')
    data = data.copy()
    data['features'] = data.apply(lambda x: _calculate_feats(x, frame_length, nfilt, rate), axis=1)
    data = data.drop(['signal'], axis=1)
    data = data.dropna().reset_index(drop=True)
    return data


def normalize(data: pd.DataFrame) -> pd.DataFrame:
    '''Function for normalizing features using z-score normalization.

    Args:
        data: A pd.DataFrame containing datatset information and features generated by extract().
    
    Returns:
        A pd.DataFrame containing normalized features and metadata.
    '''

    data = data.copy()
    mean_std = data['features'].groupby(data['recording-id']).apply(_get_mean_std)
    mean_std = mean_std.reset_index()
    mean_std = mean_std.drop(['level_1'], axis=1)
    if 'recording-id' in mean_std.columns:
        data = data.merge(mean_std, on='recording-id')
    else:
        data = pd.concat([data, mean_std], axis=1)
    print('--------------- Normalizing features --------------')
    data['normalized-features'] = data.apply(_calculate_norm, axis = 1)
    data = data.drop(['features', 'mean', 'std'], axis=1)
    return data


def prep_data(data_dir: str) -> pd.DataFrame:
    '''Function for creating pd.DataFrame containing dataset information specified by Kaldi-style
    data directory.

    Args:
        data_dir: The path to the data directory.

    Returns:
        A pd.DataFrame of dataset information. For example:

            recording-id  extended filename        utterance-id  start  end  signal
        0   rec_00        ~/Documents/test_00.wav  utt_00        10     20   [-49, -43, -35...
        1   rec_00        ~/Documents/test_00.wav  utt_01        50     60   [-35, -23, -12...
        2   rec_01        ~/Documents/test_01.wav  utt_02        135    163  [25, 32, 54...

        Note that 'utterance-id', 'start' and 'end' are optional, will only appear if data directory
        contains 'segments' file.
    '''

    wav_scp, segments, _  = utils.process_data_dir(data_dir)

    # check for segments file and process if found
    if segments is None:
        print('WARNING: Segments file not found, entire audio files will be processed.')
        wav_scp = wav_scp.merge(utils.read_sigs(wav_scp))
        return wav_scp
    else:
        data = wav_scp.merge(segments)
        data = data.merge(utils.read_sigs(data))
        return data


def _calculate_feats(row: pd.DataFrame, frame_length: float, nfilt: int, rate: int) -> np.ndarray:
    '''Auxiliary function used by extract(). Extracts log-mel spectrograms from a row of a pd.DataFrame
    containing dataset information created by prep_data().

    Args:
        row: A row of a pd.DataFrame created by prep_data().
        frame_length: Length of a spectrogram feature in seconds.
        nfilt: Number of filterbanks to use.
        rate: Sample rate.

    Returns:
        An np.ndarray of features.
    '''

    sig = row['signal']
    if 'utterance-id' in row:
        id = row['utterance-id']
    else:
        id = row['recording-id']
    try:
        assert len(range(0, int(len(sig)-1 - (frame_length+0.01) * rate), int(frame_length * rate))) > 0
        feats = []
        for j in utils.progressbar(range(0, int(len(sig)-1 - (frame_length+0.01) * rate), int(frame_length * rate)), id):
            feats.append(np.flipud(logfbank(sig[j:int(j + (frame_length+0.01) * rate)], rate, nfilt=nfilt).T))
        return np.array(feats)
    except AssertionError:
        print(f'WARNING: {id} is too short to extract features, will be ignored.')


def _calculate_norm(row: pd.DataFrame) -> np.ndarray:
    '''Auxiliary function used by normalize(). Calculates the normalized features from a row of
    a pd.DataFrame containing features and mean and standard deviation information (as generated
    by _get_mean_std()).

    Args:
        row: A row of a pd.DataFrame created by extract, with additional mean and standard deviation
        columns created by  _get_mean_std().

    Returns:
        An np.ndarray containing normalized features.
    '''

    return np.array([(i - row['mean']) / row['std'] for i in row['features']])


def _get_mean_std(group: pd.core.groupby) -> pd.DataFrame:
    '''Auxiliary function used by normalize(). Calculates mean and standard deviation of a
    group of features.

    Args:
        group: A pd.GroupBy object referencing the features of a single wavefile (could be
        from multiple utterances).

    Returns:
        A pd.DataFrame with the mean and standard deviation of the group of features.
    '''

    return pd.DataFrame({'mean': [np.mean(np.vstack(group.to_numpy()))],
                         'std': [np.std(np.vstack(group.to_numpy()))]})

# Handle args when run directly
if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='extract_feats',
                                     description='Extract log-mel spectrogram features.')

    parser.add_argument('data_dir', type=str,
                        help='a path to a Kaldi-style data directory containting \'wav.scp\', and optionally \'segments\'')
    
    parser.add_argument('out_dir', type=str,
                        help='a path to an output directory where features and metadata will be saved as feats.h5')

    args = parser.parse_args()
    data = prep_data(args.data_dir)
    feats = extract(data)
    feats = normalize(feats)
    if not os.path.exists(args.out_dir):
        print(f'Directory {args.out_dir} does not exist, creating it.')
        os.mkdir(args.out_dir)
    utils.save(feats, f'{args.out_dir}/feats.h5')