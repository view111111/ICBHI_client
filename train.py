import os
import itertools
import argparse
import random
from tqdm import tqdm
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from nets.CNN import EfficientNetV2M, NASNetLarge, InceptionResNetV2, ResNet152V2
from sklearn.model_selection import train_test_split
from utils.tools import to_onehot, load_df, create_spectrograms_raw, get_annotations, get_sound_samples, save_df, f1_m, precision_m, recall_m
from sklearn.metrics import confusion_matrix, accuracy_score
import progressbar

# input argmuments
parser = argparse.ArgumentParser(description='RespireNet: Lung Sound Classification')
parser.add_argument('--lr', default = 1e-3, type=float, help='learning rate')
parser.add_argument('--image_length', default = 224, type=int, help='height and width of image')
parser.add_argument('--batch_size', default = 16, type=int, help='bacth size')
parser.add_argument('--epochs', default = 100, type=int, help='epochs')

parser.add_argument('--save_data_dir', type=str, help='data directory: x/x/')
parser.add_argument('--data_dir', type=str, help='data directory: x/x/ICBHI_final_database')
parser.add_argument('--model_path', type=str, help='model saving directory')

args = parser.parse_args()

################################MIXUP#####################################
def train(args):
    if os.path.exists(os.path.join(args.save_data_dir, 'test_data.pkz')):
        test_data = load_df(os.path.join(args.save_data_dir, 'test_data.pkz'))
        test_label = load_df(os.path.join(args.save_data_dir, 'test_label.pkz'))
        train_data = load_df(os.path.join(args.save_data_dir, 'train_data.pkz'))
        train_label = load_df(os.path.join(args.save_data_dir, 'train_label.pkz'))
    else:
        print('\n' + '-'*10 + 'CATAGORIZE DATA' + '-'*10)
        files_name = []
        for i in os.listdir(args.data_dir):
            tail = i.split('.')[-1]
            head = i.split('.')[0]
            if tail == 'wav':
                files_name.append(head)

        # label (before onehot): normal, crackles, wheezes, both = 0, 1, 2, 3
        labels_data = {0: [], 1: [], 2: [], 3: []}
        for file_name in files_name:
            audio_file = file_name + '.wav'
            txt_file = file_name + '.txt'
            annotations = get_annotations(txt_file, args.data_dir)
            labels_data = get_sound_samples(labels_data, annotations, audio_file, args.data_dir, sample_rate=4000)

        test_data = []
        test_label = []
        train_data = []
        train_label = []
        for name in labels_data:
            all_data = labels_data[name]
            label = [name]*len(all_data)
            all_label = np.array([to_onehot(i) for i in label])
            
            X_train, X_test, y_train, y_test = train_test_split(all_data, all_label, test_size=0.2, random_state=42) # 80% for train, 20% for test

            if train_data == []:
                train_data = X_train
                train_label = y_train
            else:
                train_data = np.concatenate((train_data, X_train))
                train_label = np.concatenate((train_label, y_train))

            if test_data == []:
                test_data = X_test
                test_label = y_test
            else:
                test_data = np.concatenate((test_data, X_test))
                test_label = np.concatenate((test_label, y_test))

        save_df(test_data, os.path.join(args.save_data_dir, 'test_data.pkz'))
        save_df(test_label, os.path.join(args.save_data_dir, 'test_label.pkz'))
        save_df(train_data, os.path.join(args.save_data_dir, 'train_data.pkz'))
        save_df(train_label, os.path.join(args.save_data_dir, 'train_label.pkz'))
        print('\n' + '-'*10 + 'SAVED DATA' + '-'*10)
    
    if os.path.join(args.save_data_dir, 'image_test_data.pkz'):
      image_test_data = load_df(os.path.join(args.save_data_dir, 'image_test_data.pkz'))
      image_train_data = load_df(os.path.join(args.save_data_dir, 'image_train_data.pkz'))
    else:
      image_test_data = []
      image_train_data = []
      
      print('\n' + 'Convert test data: ...')
      p_te = progressbar.ProgressBar(maxval=len(test_data), widgets=[progressbar.Bar('=', '[', ']'), ' ', progressbar.Percentage()])
      p_te.start()
      for idx_te, te in enumerate(test_data):
          p_te.update(idx_te+1)
          if len(image_test_data) == 0:
              image_test_data = create_spectrograms_raw(te)
          else:
              image_test_data = np.concatenate((image_test_data, create_spectrograms_raw(te, n_mels=args.image_length)), axis=0)
      p_te.finish()

      print('\n' + 'Convert train data: ...')
      p_tra = progressbar.ProgressBar(maxval=len(train_data), widgets=[progressbar.Bar('=', '[', ']'), ' ', progressbar.Percentage()])
      p_tra.start()      
      for idx_tra, tra in enumerate(train_data):
          p_tra.update(idx_tra+1)
          if len(image_train_data) == 0:
              image_train_data = create_spectrograms_raw(tra)
          else:
              image_train_data = np.concatenate((image_train_data, create_spectrograms_raw(tra, n_mels=args.image_length)), axis=0)
      p_tra.finish()

      save_df(image_test_data, os.path.join(args.save_data_dir, 'image_test_data.pkz'))
      save_df(image_train_data, os.path.join(args.save_data_dir, 'image_train_data.pkz'))

    model = EfficientNetV2M(args.image_length, True)
    model.compile(optimizer="Adam", loss='categorical_crossentropy', metrics=['acc', f1_m, precision_m, recall_m]) 
    model.summary()
    history = model.fit(image_train_data, train_label,
                        epochs     = args.epochs,
                        batch_size = args.batch_size,)
    model.save(os.path.join(args.model_path, 'model.h5'))
    
    print('-'*10 + 'Test phase' + '-'*10)
    model = EfficientNetV2M(args.image_length, False)
    model.load_weights(os.path.join(args.model_path, 'model.h5'))
    _, test_acc,  test_f1_m,  test_precision_m,  test_recall_m  = model.evaluate(image_test_data, test_label, verbose=0)
    test_acc = round(test_acc, 2)
    test_f1_m = round(test_f1_m, 2)
    test_precision_m = round(test_precision_m, 2)
    test_recall_m = round(test_recall_m, 2)
    print(f'\nAccuracy: {test_acc} \t f1: {test_f1_m} \t precision: {test_precision_m} \t recall: {test_recall_m}\n')

if __name__ == "__main__":
    train(args)
