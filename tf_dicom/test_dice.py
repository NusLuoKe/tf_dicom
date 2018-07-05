#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/7/2 10:03
# @File    : test_dice.py
# @Author  : NUS_LuoKe

import tensorflow as tf
import tensorlayer as tl

from tf_dicom import u_net
from tf_dicom.load_dicom import *

# base_dir = "F:/IRCAD/3Dircadb1/"
base_dir = "/home/guest/notebooks/datasets/3Dircadb"

gpu_id = "0"
length = 512
width = 512
channel = 1
save_test_result = False

# get test set from patient_19
test_slice_path_list, test_mask_path_list = get_slice_mask_path(base_dir, patient_id_list=[19], shuffle=False)


def dice_coe(output, target, loss_type='jaccard', axis=(1, 2, 3), smooth=1e-5):
    inse = tf.reduce_sum(output * target, axis=axis)
    if loss_type == 'jaccard':
        l = tf.reduce_sum(output * output, axis=axis)
        r = tf.reduce_sum(target * target, axis=axis)
    elif loss_type == 'sorensen':
        l = tf.reduce_sum(output, axis=axis)
        r = tf.reduce_sum(target, axis=axis)
    else:
        raise Exception("Unknow loss_type")

    dice = (2. * inse + smooth) / (l + r + smooth)
    dice = tf.reduce_mean(dice)
    return dice


def dice_hard_coe(output, target, threshold=0.5, axis=(1, 2, 3), smooth=1e-5):
    output = tf.cast(output > threshold, dtype=tf.float32)
    target = tf.cast(target > threshold, dtype=tf.float32)
    inse = tf.reduce_sum(tf.multiply(output, target), axis=axis)
    l = tf.reduce_sum(output, axis=axis)
    r = tf.reduce_sum(target, axis=axis)
    hard_dice = (2. * inse + smooth) / (l + r + smooth)
    # hard_dice = tf.reduce_mean(hard_dice)
    return hard_dice


def prediction(gpu_id="0"):
    # GPU limit
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu_id
    config = tf.ConfigProto(allow_soft_placement=True)
    config.gpu_options.per_process_gpu_memory_fraction = 0.9

    # define placeholder
    x_img = tf.placeholder(tf.float32, shape=[None, length, width, channel])
    y_true = tf.placeholder(tf.float32, shape=[None, length, width, channel])

    # 1. Forward propagation
    pred = u_net.DenseNet(x_img, reduction=0.5)  # DenseNet_121(x_img, n_classes=3, is_train=True)
    y_pred = pred.outputs  # (batch_size, 512, 512, 1)

    # 2. loss
    loss_ce = tf.reduce_mean(
        tf.reduce_sum(tf.nn.sigmoid_cross_entropy_with_logits(labels=y_true, logits=y_pred), axis=(1, 2, 3)))
    loss_dice = 1 - dice_coe(tf.sigmoid(y_pred), y_true)
    # loss = loss_dice + loss_ce
    loss = loss_dice

    # 3. dice
    sig_y_pred = tf.sigmoid(y_pred)
    dice = dice_hard_coe(sig_y_pred, y_true, threshold=0.5)

    # 4. optimizer
    learning_rate = 1e-4
    # train_op = tf.train.AdamOptimizer(learning_rate).minimize(loss)
    train_op = tf.train.GradientDescentOptimizer(learning_rate).minimize(loss)

    # saver
    saver = tf.train.Saver()

    with tf.Session(config=config) as sess:
        # restore
        ckpt_path = "./save_model_and_exp_log/1st_version"
        saver.restore(sess, tf.train.latest_checkpoint(ckpt_path))
        print("load checkpoint successfully...!")
        print("start to make prediction...")

        for test_slice_path in test_slice_path_list:
            # slice
            slice = pydicom.read_file(test_slice_path)
            image_array = slice.pixel_array
            image_array[image_array < -1024] = -1024
            image_array[image_array > 1024] = 1024
            image_array = (image_array + 1024.) / 2048.
            test_batch_x = image_array.reshape((1, slice.pixel_array.shape[0], slice.pixel_array.shape[1], 1))
            idx = test_slice_path_list.index(test_slice_path)
            # mask
            mask = pydicom.read_file(test_mask_path_list[idx])
            mask_array = mask.pixel_array
            mask_array[image_array > 0] = 0
            test_batch_y = mask_array.reshape((1, mask.pixel_array.shape[0], mask.pixel_array.shape[1], 1))

            test_loss, test_dice, sig_y_pred_ = sess.run([loss, dice, sig_y_pred],
                                                         feed_dict={x_img: test_batch_x, y_true: test_batch_y})

            sig_y_pred_[sig_y_pred_ > 0.5] = 1
            sig_y_pred_[sig_y_pred_ < 0.5] = 0
            if save_test_result:
                test_image_path = test_slice_path_list[idx]
                image = pydicom.read_file(test_image_path)
                image.pixel_array.flat = np.int16(sig_y_pred_[0].reshape(y_pred[0].shape[0], y_pred[0].shape[1]))
                image.PixelData = image.pixel_array.tostring()
                save_dir = "./prediction_results"
                if not os.path.isdir(save_dir):
                    os.mkdir(save_dir)
                image.save_as(
                    os.path.join(save_dir,
                                 "image_{}".format(os.path.basename(test_slice_path_list[idx]).split("_")[1])))
                print('test loss = %.8f, test dice = %.8f' % (
                    test_loss, np.mean(test_dice[np.sum(test_batch_y, axis=(1, 2, 3)) > 0])),
                      "image_{}".format(os.path.basename(test_slice_path_list[idx]).split("_")[1]), idx)

    print("*" * 30)
    print("*" * 30)


if __name__ == '__main__':
    prediction(gpu_id)
