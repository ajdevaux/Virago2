#! /usr/local/bin/python3
from __future__ import division
import matplotlib.pyplot as plt
# import pandas as pd
import numpy as np
from scipy.ndimage import zoom
from scipy.stats import norm, gamma
from skimage.exposure import cumulative_distribution, equalize_adapthist, rescale_intensity
from skimage.feature import match_template, peak_local_max
from skimage.transform import hough_circle, hough_circle_peaks
import math, warnings

import cv2
# from clahe import clahe
# from vpipes import _dict_matcher
#*********************************************************************************************#
#
#           SUBROUTINES
#
#*********************************************************************************************#
def _gen_img_fig(img, dpi = 96):

    nrows, ncols = img.shape[0], img.shape[1]
    fig = plt.figure(figsize=(ncols/dpi, nrows/dpi), dpi=dpi)
    axes = plt.Axes(fig,[0,0,1,1])
    fig.add_axes(axes)
    axes.set_axis_off()
    axes.imshow(img, cmap=plt.cm.gray)

    return fig, axes
#*********************************************************************************************#
def image_details(fig1, fig2, fig3, pic_canny, save = False,  chip_name ='', png='', dpi = 96):
    """A subroutine for debugging contrast adjustment"""
    bin_no = 150
    nrows, ncols = fig1.shape
    fig = plt.figure(figsize = (ncols/dpi/2, nrows/dpi/2), dpi = dpi)
    ax_img = plt.Axes(fig,[0,0,1,1])
    fig.add_axes(ax_img)
    ax_img.set_axis_off()
    ax_img.imshow(fig3, cmap = 'gray')

    fig3[pic_canny] = fig3.max()*2



    pic_cdf1, cbins1 = cumulative_distribution(fig1, bin_no)
    pic_cdf2, cbins2 = cumulative_distribution(fig2, bin_no)
    pic_cdf3, cbins3 = cumulative_distribution(fig3, bin_no)

    ax_hist1 = plt.axes([.05, .05, .25, .25])
    ax_cdf1 = ax_hist1.twinx()
    ax_hist2 = plt.axes([.375, .05, .25, .25])
    ax_cdf2 = ax_hist2.twinx()
    ax_hist3 = plt.axes([.7, .05, .25, .25])
    ax_cdf3 = ax_hist3.twinx()

    fig1r = fig1.ravel(); fig2r = fig2.ravel(); fig3r = fig3.ravel()

    hist1, hbins1, __ = ax_hist1.hist(fig1r, bin_no, facecolor = 'r', normed = True)
    hist2, hbins2, __ = ax_hist2.hist(fig2r, bin_no, facecolor = 'b', normed = True)
    hist3, hbins3, __ = ax_hist3.hist(fig3r, bin_no, facecolor = 'g', normed = True)

    ax_hist1.patch.set_alpha(0); ax_hist2.patch.set_alpha(0); ax_hist3.patch.set_alpha(0)

    ax_cdf1.plot(cbins1, pic_cdf1, color = 'w')
    ax_cdf2.plot(cbins2, pic_cdf2, color = 'c')
    ax_cdf3.plot(cbins3, pic_cdf3, color = 'y')

    bin_centers2 = 0.5*(hbins2[1:] + hbins2[:-1])
    m2, s2 = norm.fit(fig2r)
    pdf2 = norm.pdf(bin_centers2, m2, s2)
    ax_hist2.plot(bin_centers2, pdf2, color = 'm')
    mean, var, skew, kurt = gamma.stats(fig2r, moments='mvsk')
    # print(mean, var, skew, kurt)

    ax_hist1.set_title("Normalized", color = 'r')
    ax_hist2.set_title("CLAHE Equalized", color = 'b')
    ax_hist3.set_title("Contrast Stretched", color = 'g')

    ax_hist1.set_ylim([0,max(hist1)])
    ax_hist2.set_ylim([0,max(hist2)])
    ax_hist3.set_ylim([0,max(hist3)])

    ax_hist1.set_xlim([np.median(fig1)-0.1,np.median(fig1)+0.1])
    ax_hist2.set_xlim([np.median(fig2)-0.1,np.median(fig2)+0.1])
    ax_hist3.set_xlim([0,1])
    #ax_cdf1.set_ylim([0,1])

    ax_hist1.tick_params(labelcolor='tab:orange')

    if save == True:
        plt.savefig('../virago_output/' + chip_name
                    + '/processed_images/' + png
                    + '_image_details.png',
                    dpi = dpi)
    plt.show()

    plt.close('all'); plt.clf()
    # return hbins2, pic_cdf1
#*********************************************************************************************#
def gen_img_deets(img, name ='', savedir='', dpi = 96):
    """A subroutine for debugging contrast adjustment"""
    bin_no = 256

    _gen_img_fig(img)

    ax_hist2 = plt.axes([.100, .05, .25, .25])
    ax_cdf2 = ax_hist2.twinx()


    img_ravelled = img.ravel()
    hist1, hbins1, __ = ax_hist2.hist(img_ravelled, bin_no, facecolor = 'r', normed = True)
    bin_centers = 0.5*(hbins1[1:] + hbins1[:-1])
    m, s = norm.fit(img_ravelled)
    pdf = norm.pdf(bin_centers, m, s)


    pic_cdf1, cbins1 = cumulative_distribution(img, bin_no)
    ax_cdf2.plot(cbins1, pic_cdf1, color = 'w')

    ax_hist2.plot(bin_centers, pdf, color = 'm')
    ax_hist2.patch.set_alpha(0);
    ax_hist2.set_ylim([0,max(hist1)])

    ax_hist2.set_xlim([np.min(img),np.max(img)])
    ax_hist2.tick_params(labelcolor='tab:orange')

    if savedir:
        plt.savefig('{}/{}.png'.format(savedir, name), dpi = dpi)
        print("\nFile generated: {}.png\n".format(name))
    else:
        plt.show()

    plt.close('all'); plt.clf()
#*********************************************************************************************#

def gen_img(image, name='img_name', savedir='', dpi=96):
    _gen_img_fig(image)
    if savedir:
        plt.savefig('{}/{}.png'.format(savedir, name), dpi = dpi)
        print("\nFile generated: {}.png\n".format(name))
    else:
        plt.show()

    plt.close('all')
#*********************************************************************************************#
def gen_img3D(im3D, cmap = "gray", step = 1):
    """Debugging function for viewing all image files in a stack"""
    _, axes = plt.subplots(nrows = int(np.ceil(zslice_count/4)),
                           ncols = 4,
                           figsize = (16, 14))
    vmin = im3D.min()
    vmax = im3D.max()

    for ax, image in zip(axes.flatten(), im3D[::step]):
        ax.imshow(image, cmap=cmap, vmin=vmin, vmax=vmax)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_axis_off()

    plt.show()
    plt.close('all')
#*********************************************************************************************#
def marker_finder(image, marker, thresh = 0.9):
    """This locates the "backwards-L" shapes in the IRIS images"""

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        warnings.warn(FutureWarning)##Numpy FFT Warning. This is Scikit-Image's problem
        if marker.ndim == 2:

            locs = peak_local_max(match_template(image, marker, pad_input = True),
                                  min_distance = 775,
                                  threshold_rel = thresh,
                                  exclude_border = False,
                                  num_peaks = 4
            )

        elif marker.ndim == 3:

            locs = [peak_local_max(match_template(image, m, pad_input = True),
                                                  threshold_rel = thresh - 0.2,
                                                  exclude_border = False,
                                                  num_peaks = 1
                                    ).flatten() for m in marker
            ]

    locs = list(map(lambda x: tuple(x), locs))
    locs.sort(key = lambda coord: coord[1])
    print(locs)
    return locs
#*********************************************************************************************#
def marker_masker(image, locs, marker):
    if marker.ndim == 2:
        h, w = marker.shape
    else:
        z, h, w = marker.shape

    mask = np.zeros(shape = image.shape, dtype = bool)

    found_markers = np.empty([len(locs),h,w], dtype = 'float64')
    bad_locs,bad_index = [],[]
    for i, coords in enumerate(locs):
        loc_y, loc_x = coords
        height, width = h/2, w/2

        marker_h = np.arange(loc_y - height, loc_y + height + 1, dtype = int)

        marker_w = np.arange(loc_x - width,  loc_x + width + 1, dtype = int)


        mask[marker_h[0]:marker_h[-1],marker_w[0]:marker_w[-1]] = True

        # gen_img(image[marker_h[0]:marker_h[-1],marker_w[0]:marker_w[-1]])
        try:
            found_markers[i] = image[marker_h[0]:marker_h[-1],marker_w[0]:marker_w[-1]]
        except ValueError:
            bad_locs.append(coords)
            bad_index.append(i)

    locs = [coords for coords in locs if coords not in bad_locs]
    found_markers = np.delete(found_markers, bad_index, axis=0)

    return mask, found_markers

#*********************************************************************************************#
def spot_finder(image, rad_range = (525, 651), Ab_spot = True):
    """Locates the antibody spot convalently bound to the SiO2 substrate
    where particles of interest should be accumulating"""
    nrows, ncols = image.shape
    if Ab_spot == False:
        xyr = (ncols/2, nrows/2, 600)
    else:
        hough_radius = range(rad_range[0], rad_range[1], 25)
        hough_res = hough_circle(image, hough_radius)
        accums, cx, cy, rad = hough_circle_peaks(hough_res, hough_radius, total_num_peaks=1)
        xyr = tuple((int(cx), int(cy), int(rad)))
    print("Spot center coordinates (row, column, radius): {}\n".format(xyr))
    return xyr
#*********************************************************************************************#
def clahe_3D(img_stack, kernel_size = [270,404], cliplim = 0.004):
    """Performs the contrast limited adaptive histogram equalization on the stack of images"""
    if img_stack.ndim == 2: img_stack = np.array([img_stack])

    img3D_clahe = np.empty_like(img_stack, dtype='float64')

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        warnings.warn(UserWarning)##Images are acutally converted to uint16 for some reason

        for plane, image in enumerate(img_stack):
            img3D_clahe[plane] = equalize_adapthist(image, kernel_size, clip_limit = cliplim)

    return img3D_clahe
#*********************************************************************************************#
def cv2_clahe_3D(img3D, kernel_size = (8,8), cliplim = 156):
    """Performs the contrast limited adaptive histogram equalization on the stack of images"""
    if img3D.ndim == 2: img3D = np.array([img_stack])

    clahe = cv2.createCLAHE(clipLimit=cliplim, tileGridSize=kernel_size)

    img3D_clahe = np.empty_like(img3D, dtype=img3D.dtype)
    for plane, img in enumerate(img3D):
        img3D_clahe[plane] = clahe.apply(img)

    return img3D_clahe
#*********************************************************************************************#
def rescale_3D(img_stack, perc_range = (2,98)):
    """Streches the histogram for all images in stack to further increase contrast"""
    img3D_rescale = np.empty_like(img_stack)
    for plane, image in enumerate(img_stack):
        p1,p2 = np.percentile(image, perc_range)
        img3D_rescale[plane] = rescale_intensity(image, in_range=(p1,p2))
    return img3D_rescale
#*********************************************************************************************#
def cv2_rescale_3D(img_stack):
    """Streches the histogram for all images in stack to further increase contrast"""
    img3D_rescale = np.empty_like(img_stack)
    for plane, image in enumerate(img_stack):
        img3D_rescale[plane] = cv2.equalizeHist(image)
    return img3D_rescale
#*********************************************************************************************#
def masker_3D(image_stack, mask, filled = False, fill_val = 0):
    """Masks all images in stack so only areas not masked (the spot) are quantified.
    Setting filled = True will return a normal array with fill_val filled in on the masked areas.
    Default filled = False returns a numpy masked array."""

    pic3D_masked = np.ma.empty_like(image_stack)
    pic3D_filled = np.empty_like(image_stack)

    for plane, image in enumerate(image_stack):
        pic3D_masked[plane] = np.ma.array(image, mask = mask)
        if filled == True:
            pic3D_filled[plane] = pic3D_masked[plane].filled(fill_value = fill_val)

    if filled == False:
        return pic3D_masked
    else:
        return pic3D_filled
#*********************************************************************************************#
def measure_rotation(marker_dict, spot_pass_str):
    """Measures how rotated the image is compared to the previous scan"""
    marker_ct = len(marker_dict[spot_pass_str])
    if marker_ct == 2:
        r1 = marker_dict[spot_pass_str][0][0]
        r2 = marker_dict[spot_pass_str][1][0]
        c1 = marker_dict[spot_pass_str][0][1]
        c2 = marker_dict[spot_pass_str][1][1]
        row_diff = abs(r1 - r2)
        col_diff = abs(c1 - c2)
        if (col_diff < row_diff) & (col_diff < 15):
            print("Markers vertically aligned")
            img_rot_deg = math.degrees(math.atan(col_diff / row_diff))
            print("\nImage rotation: {} degrees\n".format(round(img_rot_deg,3)))
        elif (row_diff < col_diff) & (row_diff < 15):
            print("Markers horizontally aligned")
            img_rot_deg = math.degrees(math.atan(row_diff / col_diff))
            print("\nImage rotation: {} degrees\n".format(round(img_rot_deg,3)))
        else:
            print("Markers unaligned; cannot compute rotation")
            img_rot_deg = np.nan
    else:
        print("Wrong number of markers ({}); cannot compute rotation".format(marker_ct))
        img_rot_deg = np.nan
    return img_rot_deg
#*********************************************************************************************#
def _dict_matcher(_dict, spot_num, pass_num, mode = 'series'):
    """Sub-function for retreving the marker locations (R,C format) of the two images being compared"""
    if mode == 'baseline':
        prev_pass = 1
    elif mode == 'series':
        prev_pass = pass_num - 1

    for key in _dict.keys():
        key0, key1 = map(lambda x: int(x), key.split('.'))
        if (key0 == spot_num) & (key1 == prev_pass):
            prev_vals = _dict[key]
        elif (key0 == spot_num) & (key1 == pass_num):
            new_vals = _dict[key]
    return prev_vals, new_vals
#*********************************************************************************************#
def measure_shift(marker_dict, pass_num, spot_num, mode = 'baseline'):
    """Measures the Row, Column shift of pixels between the original image and the subsequent image"""
    overlay_toggle = True

    prev_locs, new_locs = _dict_matcher(marker_dict, spot_num, pass_num, mode = mode)
    plocs_ct = len(prev_locs)
    nlocs_ct = len(new_locs)

    if plocs_ct != nlocs_ct:
        max_shift = 100
    else:
        max_shift = 150

    if (plocs_ct > 0) & (nlocs_ct > 0):
        shift_array = np.asarray([np.subtract(coords1, coords0)
                                  for coords0 in prev_locs
                                  for coords1 in new_locs
                                  if np.all(abs(np.subtract(coords1, coords0)) <= max_shift)
        ])
    else:
        shift_array = np.asarray([])

    if shift_array.size > 0:
        mean_shift = np.mean(shift_array, axis = 0)
        overlay_toggle = True
    else:
        mean_shift = (0,0)
        overlay_toggle = False
    # else:
    #     mean_shift =
    #     overlay_toggle = True


    return tuple(mean_shift), overlay_toggle
#*********************************************************************************************#
def measure_shift_ORB(img1, img2, ham_thresh=10, show=False):
    match_ct = 0
    while match_ct <= 2:
        #Convert images to 8-bit for OpenCV compatibility
        img1=np.uint8(cv2.normalize(img1, None, 0, 255, cv2.NORM_MINMAX))
        img2=np.uint8(cv2.normalize(img2, None, 0, 255, cv2.NORM_MINMAX))

        # Initiate ORB detector
        orb = cv2.ORB_create()

        # find the keypoints and descriptors with ORB
        kp1, des1 = orb.detectAndCompute(img1,None)
        kp2, des2 = orb.detectAndCompute(img2,None)

        # create BFMatcher object
        bruteforce = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

        # Match descriptors
        matches = bruteforce.match(des1,des2)
        #Throw out all but best descriptors based on Hamming distance
        matches = [match for match in matches if match.distance <= ham_thresh]

        match_ct = len(matches)
        #Increase threshold until a few matches are found
        if match_ct <= 2:
            ham_thresh += 2
            print("No matches... increasing Hamming distance threshold to {}\n".format(ham_thresh))

    print('Matched {} descriptors'.format(match_ct))

    # Sort them in the order of their Hamming distance.
    # matches = sorted(matches, key = lambda x:x.distance)

    #Measure the pixel shift for each descriptor
    shift_array = np.array([np.subtract(kp2[mat.trainIdx].pt, kp1[mat.queryIdx].pt) for mat in matches])

    #Get the median value of all measured shifts and convert into a Row, Column format tuple


    # Draw first 20 matches.
    if show == True:
        fig, ax = plt.subplots(nrows=1, ncols=1)
        img3 = cv2.drawMatches(img1,kp1,img2,kp2,matches, None, flags=2)
        # ax.axis('off')
        # ax.set_title("Prescan / Postscan")

        plt.imshow(img3),plt.show()

    return (round(np.median(shift_array[:,1]),0), round(np.median(shift_array[:,0]),0))
#*********************************************************************************************#
def overlayer(bot_img, top_img, mean_shift):

    nrows, ncols = bot_img.shape

    vshift, hshift = mean_shift
    vshift = int(math.ceil(vshift))
    hshift = int(math.ceil(hshift))

    try:
        bot_img
    except NameError:
        print("Cannot overlay images")
    else:
        if vshift < 0:
            vshift = abs(vshift)
            bot_img = np.delete(bot_img, np.s_[0:vshift], axis = 0)
            bot_img = np.append(bot_img, np.zeros((vshift,ncols)), axis=0)
            # top_img = np.delete(top_img, np.s_[-vshift:], axis = 0)
        elif vshift > 0:
            bot_img = np.delete(bot_img, np.s_[-vshift:], axis = 0)
            bot_img = np.insert(bot_img, 0, np.zeros((vshift,ncols)), axis = 0)
            # top_img = np.delete(top_img, np.s_[0:vshift], axis = 0)

        if hshift < 0:
            hshift = abs(hshift)
            bot_img = np.delete(bot_img, np.s_[0:hshift], axis = 1)
            bot_img = np.append(bot_img, np.zeros((nrows,hshift)), axis=1)
            # top_img = np.delete(top_img, np.s_[-abs(hshift):], axis = 1)
        elif hshift > 0:
            bot_img = np.delete(bot_img, np.s_[-hshift:], axis = 1)
            bot_img = np.insert(bot_img, [0], np.zeros((nrows,hshift)), axis=1)
            # top_img = np.delete(top_img, np.s_[0:abs(hshift)], axis = 1)

        return np.dstack((bot_img, top_img, np.zeros_like(bot_img)))

#*********************************************************************************************#
def prescan_subtractor(overlay_dict, overlay_toggle, spot_num, pass_num, mean_shift, mode ='baseline'):
    vshift = int(np.ceil(mean_shift[0]))
    hshift = int(np.ceil(mean_shift[1]))
    if (pass_num > 1) & (overlay_toggle == True):
        bot_img, top_img = _dict_matcher(overlay_dict, spot_num, pass_num, mode = mode)

        try: bot_img
        except NameError: print("Cannot overlay images")
        else:
            if vshift < 0:
                bot_img = np.delete(bot_img, np.s_[0:abs(vshift)], axis = 0)
                top_img = np.delete(top_img, np.s_[-abs(vshift):], axis = 0)
            elif vshift > 0:
                bot_img = np.delete(bot_img, np.s_[-abs(vshift):], axis = 0)
                top_img = np.delete(top_img, np.s_[0:abs(vshift)], axis = 0)
            if hshift < 0:
                bot_img = np.delete(bot_img, np.s_[0:abs(hshift)], axis = 1)
                top_img = np.delete(top_img, np.s_[-abs(hshift):], axis = 1)
            elif hshift >0:
                bot_img = np.delete(bot_img, np.s_[-abs(hshift):], axis = 1)
                top_img = np.delete(top_img, np.s_[0:abs(hshift)], axis = 1)

            prescan_subtraction = top_img - bot_img

            return image_overlay

    elif pass_num == 1:
        print("First scan of spot...")
    else:
        print("Cannot overlay images")
#*********************************************************************************************#
def cropper(pic, coords, img_dir, crop_pix = 150, zoom_amt = 1):
    crop_dict = {}
    cx = int(coords[0])
    cy = int(coords[1])
    rad = int(coords[2])
    for i in range(-300,301,150):

        sx = cx + i
        sy = cy + i

        print(i)
        print(sx, cy)
        print(cx, sy)
        if not (sx,cy) == (cx,sy):
            gen_img(pic[cy-crop_pix: cy+crop_pix, sx-crop_pix: sx+crop_pix],
                            name = "{}.{}-{}".format(img_name,cy,sx),
                            savedir = img_dir,
                            # zoom_amt = zoom_amt

            )
            gen_img(pic[sy-crop_pix: sy+crop_pix, cx-crop_pix: cx+crop_pix],
                            name = "{}.{}-{}".format(img_name,sy,cx),
                            savedir = img_dir,
            )
        else:
            gen_img(pic[cy-crop_pix: cy+crop_pix, cx-crop_pix: cx+crop_pix],
                            name = "{}.{}-{}".format(img_name,cy,cx),
                            savedir = img_dir
            )
#*********************************************************************************************#
def shape_mask_shift(shape_mask, mean_shift):
    """
    Shifts the before-and-after images so that old particles will be masked and not counted in
    the new image
    """
    vshift = int(np.ceil(mean_shift[0]))
    hshift = int(np.ceil(mean_shift[1]))

    if vshift > 0:
        shape_mask = np.delete(shape_mask, np.s_[-abs(vshift):], axis = 0)
        shape_mask = np.insert(shape_mask, np.s_[0:abs(vshift)], False, axis = 0)
    elif vshift < 0:
        shape_mask = np.delete(shape_mask, np.s_[0:abs(vshift)], axis = 0)
        shape_mask = np.insert(shape_mask, np.s_[-abs(vshift):], False, axis = 0)

    if hshift > 0:
        shape_mask = np.delete(shape_mask, np.s_[-abs(hshift):], axis = 1)
        shape_mask = np.insert(shape_mask, np.s_[0:abs(hshift)], False, axis = 1)
    elif hshift < 0:
        shape_mask = np.delete(shape_mask, np.s_[0:abs(hshift)], axis = 1)
        shape_mask = np.insert(shape_mask, np.s_[-abs(hshift):], False, axis = 1)

    return shape_mask
#*********************************************************************************************#
