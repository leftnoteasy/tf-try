import numpy as np
import pandas as pd
import dicom
import os
import matplotlib.pyplot as plt
import cv2
import math
import tensorflow as tf
import numpy as np

"""
Define flags
"""

tf.app.flags.DEFINE_string("data_dir", "",
                           "absolute path to where parent dir of data, used in preprocessing")
tf.app.flags.DEFINE_string("label_csv_path", "",
                           "path to label csv, used in preprocessing")
tf.app.flags.DEFINE_string("processed_data_path", "",
                           "where to save/load processed data")

tf.app.flags.DEFINE_integer("num_patient_training", 0,
                            "Numer of patient to do training")
tf.app.flags.DEFINE_integer("num_patient_validation", 0,
                            "Numer of patient to do validation")

tf.app.flags.DEFINE_string("task", "training", "Value from train|preprocess")

FLAGS = tf.app.flags.FLAGS

"""
Constants
"""

IMG_SIZE_PX = 50
SLICE_COUNT = 20

n_classes = 2
batch_size = 10

keep_rate = 0.8


def chunks(l, n):
    # Credit: Ned Batchelder
    # Link: http://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]


def mean(a):
    return sum(a) / len(a)


def process_data(patient, labels_df, img_px_size=50, hm_slices=20, visualize=False):
    label = labels_df.get_value(patient, 'cancer')
    path = FLAGS.data_dir + patient
    slices = [dicom.read_file(path + '/' + s) for s in os.listdir(path)]
    slices.sort(key=lambda x: int(x.ImagePositionPatient[2]))

    new_slices = []
    slices = [cv2.resize(np.array(each_slice.pixel_array), (img_px_size, img_px_size)) for each_slice in slices]

    chunk_sizes = int(math.ceil(len(slices) / hm_slices))
    for slice_chunk in chunks(slices, chunk_sizes):
        slice_chunk = list(map(mean, zip(*slice_chunk)))
        new_slices.append(slice_chunk)

    if len(new_slices) == hm_slices - 1:
        new_slices.append(new_slices[-1])

    if len(new_slices) == hm_slices - 2:
        new_slices.append(new_slices[-1])
        new_slices.append(new_slices[-1])

    if len(new_slices) == hm_slices + 2:
        new_val = list(map(mean, zip(*[new_slices[hm_slices - 1], new_slices[hm_slices], ])))
        del new_slices[hm_slices]
        new_slices[hm_slices - 1] = new_val

    if len(new_slices) == hm_slices + 1:
        new_val = list(map(mean, zip(*[new_slices[hm_slices - 1], new_slices[hm_slices], ])))
        del new_slices[hm_slices]
        new_slices[hm_slices - 1] = new_val

    if visualize:
        fig = plt.figure()
        for num, each_slice in enumerate(new_slices):
            y = fig.add_subplot(4, 5, num + 1)
            y.imshow(each_slice, cmap='gray')
        plt.show()

    if label == 1:
        label = np.array([0, 1])
    elif label == 0:
        label = np.array([1, 0])

    return np.array(new_slices), label


def conv3d(x, W):
    return tf.nn.conv3d(x, W, strides=[1, 1, 1, 1, 1], padding='SAME')


def maxpool3d(x):
    #                        size of window         movement of window as you slide about
    return tf.nn.max_pool3d(x, ksize=[1, 2, 2, 2, 1], strides=[1, 2, 2, 2, 1], padding='SAME')


def convolutional_neural_network(x):
    #                # 5 x 5 x 5 patches, 1 channel, 32 features to compute.
    weights = {'W_conv1': tf.Variable(tf.random_normal([3, 3, 3, 1, 32])),
               #       5 x 5 x 5 patches, 32 channels, 64 features to compute.
               'W_conv2': tf.Variable(tf.random_normal([3, 3, 3, 32, 64])),
               #                                  64 features
               'W_fc': tf.Variable(tf.random_normal([54080, 1024])),
               'out': tf.Variable(tf.random_normal([1024, n_classes]))}

    biases = {'b_conv1': tf.Variable(tf.random_normal([32])),
              'b_conv2': tf.Variable(tf.random_normal([64])),
              'b_fc': tf.Variable(tf.random_normal([1024])),
              'out': tf.Variable(tf.random_normal([n_classes]))}

    #                            image X      image Y        image Z
    x = tf.reshape(x, shape=[-1, IMG_SIZE_PX, IMG_SIZE_PX, SLICE_COUNT, 1])

    conv1 = tf.nn.relu(conv3d(x, weights['W_conv1']) + biases['b_conv1'])
    conv1 = maxpool3d(conv1)

    conv2 = tf.nn.relu(conv3d(conv1, weights['W_conv2']) + biases['b_conv2'])
    conv2 = maxpool3d(conv2)

    fc = tf.reshape(conv2, [-1, 54080])
    fc = tf.nn.relu(tf.matmul(fc, weights['W_fc']) + biases['b_fc'])
    fc = tf.nn.dropout(fc, keep_rate)

    output = tf.matmul(fc, weights['out']) + biases['out']

    return output


def train_neural_network(x):
    print(x.get_shape())
    prediction = convolutional_neural_network(x)
    cost = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(prediction, y))
    optimizer = tf.train.AdamOptimizer(learning_rate=1e-3).minimize(cost)

    hm_epochs = 10
    with tf.Session() as sess:
        sess.run(tf.initialize_all_variables())

        successful_runs = 0
        total_runs = 0

        for epoch in range(hm_epochs):
            epoch_loss = 0
            for data in train_data:
                total_runs += 1
                try:
                    X = data[0]
                    Y = data[1]
                    _, c = sess.run([optimizer, cost], feed_dict={x: X, y: Y})
                    epoch_loss += c
                    successful_runs += 1
                except Exception as e:
                    # I am passing for the sake of notebook space, but we are getting 1 shaping issue from one
                    # input tensor. Not sure why, will have to look into it. Guessing it's
                    # one of the depths that doesn't come to 20.
                    # print(str(e))
                    pass

            print('Epoch', epoch + 1, 'completed out of', hm_epochs, 'loss:', epoch_loss)

            correct = tf.equal(tf.argmax(prediction, 1), tf.argmax(y, 1))
            accuracy = tf.reduce_mean(tf.cast(correct, 'float'))

            for i in validation_data:
                print(i[0].shape)

            print('Accuracy:', accuracy.eval({x: [i[0] for i in validation_data], y: [i[1] for i in validation_data]}))
            # print('Accuracy:',accuracy)

        print('Done. Finishing accuracy:')
        print('Accuracy:', accuracy.eval({x: [i[0] for i in validation_data], y: [i[1] for i in validation_data]}))
        # print('Accuracy:',accuracy)

        print('fitment percent:', successful_runs / total_runs)


if __name__ == "__main__":
    if FLAGS.task == "train":
        x = tf.placeholder('float')
        y = tf.placeholder('float')

        much_data = np.load(FLAGS.processed_data_path)

        num_training = FLAGS.num_patient_training
        num_validation = FLAGS.num_patient_validation

        if num_training + num_validation > len(much_data):
            raise "Number of data available less than #training + #valudation"

        # If you are working with the basic sample data, use maybe 2 instead of 100 here... you don't have enough data to really do this
        train_data = much_data[:num_training]
        train_data = [i for i in train_data if i[0].shape[0] == 20]

        validation_data = much_data[num_training:num_training + num_validation]
        validation_data = [i for i in validation_data if i[0].shape[0] == 20]

        print "Actual #items for training = " + str(len(train_data)) + ", #items for validation=" + str(len(validation_data))

        # Run this locally:
        train_neural_network(x)
    elif FLAGS.task == "preprocess":
        patients = os.listdir(FLAGS.data_dir)
        labels = pd.read_csv(FLAGS.label_csv_path, index_col=0)

        much_data = []
        for num, patient in enumerate(patients):
            if num % 100 == 0:
                print(num)
            try:
                img_data, label = process_data(patient, labels, img_px_size=IMG_SIZE_PX, hm_slices=SLICE_COUNT)
                # print(img_data.shape,label)
                much_data.append([img_data, label])
            except KeyError as e:
                print('This is unlabeled data!')

        print "Finished process data, #items in saved data=" + str(len(much_data))
        np.save(FLAGS.processed_data_path, much_data)