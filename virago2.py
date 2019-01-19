#!/usr/bin/env python3
from __future__ import division

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import glob
import os
import sys
import warnings

from future.builtins import input
from datetime import datetime
from skimage import io as skio
from skimage.filters import sobel_h, sobel_v
from skimage.feature import shape_index, canny
from skimage.measure import label, regionprops
from scipy import ndimage as ndi
from scipy.optimize import curve_fit

from modules import vpipes, vimage, vquant, vgraph
from modules.filographs import filohisto
from images import logo


pd.set_option('display.width', 1000)
pd.options.display.max_rows=999
pd.options.display.max_columns=15
logo.print_logo()
version = '2.11.0'
"""
Version 2.11.0 = Added a correlation function to better select pixels that are nanoparticles.
                  This increases analysis time. Only works with large-stack data (>21 images)
Version 2.10.8 = Modified thresholds for shape finding; narrowed the window of the maxmin projection
Version 2.10.7 = Removed for loops when doing data extraction from regionprops.
Version 2.10.6 = changed how focus is caluclated using the Tenengrad algorithm
Version 2.10.5 = Increased CLAHE clip limit from .002 to .008 for Exoviewer images to improve quality
Version 2.10.4 = Added TIFF compatibility
Version 2.10.3 = New template for Exoviewer markers
Version 2.10.2 = Lowered CV cutoff for in-liquid experiments to 0.01
Version 2.10.1 = Fixed histgrams so that values are normalized to counting area
Version 2.10 = Added filament length measurements. Still in beta.
Version 2.9 = Exoviewer & fluorescence functionality
Version 2.8 = Using mirror normalized image rather than original image for calculations
Version 2.6 = Using mask to remove old particles instead of relying on subtractions
"""
print("VERSION {}\n".format(version))
print(os.path.dirname(__file__))

def psf_sine(x,a,b,c):
    return a * np.sin(b * x + c)

def find_focus_by_3methods(pic3D):
    """
    Uses edge detection to find the image in the stack with the highest variance,
    which is deemed to have the greatest focusself.
    """
    var_vals = [np.var(sobel(image)) for image in marker_img]
    var_max = var_vals.index(max(var_vals))

    teng_vals = [np.mean(sobel_h(pic)**2 + sobel_v(pic)**2) for pic in pic3D]
    teng_max = teng_vals.index(max(teng_vals))

    laplace_vals = [laplace(pic,3).var() for pic in pic3D_rescale]
    laplace_max = laplace_vals.index(max(laplace_vals))

    top_3 = sorted(var_list, reverse = True)[:3]
    index_list = [var_list.index(val) for val in top_3]
    diff_list = [abs(pic3D.shape[0]//2 - val) for val in index_list]

    return index_list[diff_list.index(min(diff_list))]

def double_sum(pic3D):
    M = pic3D.shape[1]
    N = pic3D.shape[2]
    B_list = []
    for pic in pic3D:
        # mu = np.mean(pic)
        # coeff = 1/(M*N*mu)
        B_list.append(sum((pic[i][j] - pic[i+2][j])**2 for i in range(M-2) for j in range(N)))

#COULD BE INTERESTING
def fourier_map(pic3D):
    z, nrows, ncols = pic3D.shape
    for plane in pic3D:
        f = np.fft.fft2(plane)
        fshift = np.fft.fftshift(f)
        mag_spec = 20*np.log(np.abs(fshift))

        crow,ccol = rows//2 , cols//2
        fshift[crow-30:crow+30, ccol-30:ccol+30] = 0
        f_ishift = np.fft.ifftshift(fshift)
        img_back = np.fft.ifft2(f_ishift)
        img_back = np.abs(img_back)
        # vimage.gen_img(img_back)
        print(np.max(img_back))

    return img_back
#*********************************************************************************************#
#
#    CODE BEGINS HERE
#
#*********************************************************************************************#
##Quick-change Boolean Parameters
show_particles = True ##show particle info on output images
show_filos = True
Ab_spot_mode = True ##change to False if chips have not been spotted with antibody microarray

#*********************************************************************************************#
IRISmarker_liq = skio.imread('images/IRISmarker_new.tif')
IRISmarker_exo = skio.imread('images/IRISmarker_v4_topstack.tif')

pgm_list, tiff_list = [],[]
marker_dict = {}
while (pgm_list == []) and (tiff_list == []): ##Keep repeating until pgm files are found
    iris_path = input("\nPlease type in the path to the folder that contains the IRIS data:\n")
    if iris_path == 'test':
        iris_path = '/Volumes/KatahdinHD/ResilioSync/DATA/IRIS/FIGS4PAPER/expts/tCHIP007_EBOVmay@1E6'
    else:
        iris_path = iris_path.strip('"')##Point to the correct directory
    os.chdir(iris_path)
    pgm_list = sorted(glob.glob('*.pgm'))
    tiff_list = sorted(glob.glob('*.tif'))

pgm_list, mirror = vpipes.mirror_finder(pgm_list)

if tiff_list == []:
    tiff_toggle = False
    image_list = pgm_list

    convert_tiff = input("Convert PGM stacks to TIFFs (y/n)?")
    while convert_tiff.lower() not in ['yes', 'y', 'no', 'n']:
        convert_tiff = input("Convert PGM stacks to TIFFs (y/n)?")
    if convert_tiff in ['yes', 'y']: convert_tiff = True
    else: convert_tiff = False

elif pgm_list == []:
    tiff_toggle = True
    image_list = tiff_list

else:
    print("Mixture of PGM and TIFF files\n")#. Please convert all PGM files before continuing")
    image_list = tiff_list + pgm_list
    convert_tiff = True
    # sys.exit()


txt_list = sorted(glob.glob('*.txt'))
xml_list = sorted(glob.glob('*/*.xml'))
if not xml_list: xml_list = sorted(glob.glob('../*/*.xml'))

chip_name = image_list[0].split(".")[0]
if chip_name == 'baseCHIP404':
    Ab_spot_mode = False
image_set = set(".".join(file.split(".")[:3]) for file in image_list)

txtcheck = [file.split(".") for file in txt_list]
iris_txt = [".".join(file) for file in txtcheck if (len(file) >= 3) and (file[2].isalpha())]

xml_file = [file for file in xml_list if chip_name in file]
if xml_file:
    chipFile = vpipes.xml_parser(xml_file[0])
    meta_dict = chipFile[0]
    if meta_dict['chipversion'] == '4':
        print("Exoviewer images\n")
        if Ab_spot_mode == True:
            cliplim = 0.002
        else:
            cliplim = 0.004
        perc_range = (3,97)
        cam_micron_per_pix = 3.45 * 2
        mag = 44
        exo_toggle = True
        cv_cutoff = 0.1
        r2_cutoff = 0.85
        IRISmarker = IRISmarker_exo
        canny_sig = 2.5
        NA = 0.75
        timeseries_mode = 'scan'
        filohist_range = (0,50)

    elif meta_dict['chipversion'] == '5':
        print("In-liquid chip\n")
        cliplim = 0.004
        perc_range = (3,97)
        cam_micron_per_pix = 5.86
        mag = 40
        exo_toggle = False
        cv_cutoff = 0.01
        IRISmarker = IRISmarker_liq
        canny_sig = 1.5
        NA = 0.75
        filohist_range = (0,10)
    else:
        raise ValueError("Unknown IRIS chip version\n")

    marker_h, marker_w =  IRISmarker.shape
    hmarker_h = marker_h // 2
    hmarker_w = marker_w // 2
    mAb_dict, mAb_dict_rev = vpipes.chipFile_reader(chipFile, remove_jargon = True)
    spot_counter = len([key for key in mAb_dict])##Important

else:
    print("\nNon-standard chip\n")
    raise ValueError('Cannot find IRIS chip file')
    cam_micron_per_pix = 3.45
    mag = 44
    exo_toggle = True
    cv_cutoff = 0.1
    IRISmarker = IRISmarker_exo
    cliplim = 0.004
    timeseries_mode = 'scan'
    spot_counter = max([int(pgmfile.split(".")[1]) for imgfile in image_list])##Important

    mAb_dict = {i:i for i in range(1,spot_counter+1)}
    mAb_dict_rev = {1: list(range(1,spot_counter+1))}

if Ab_spot_mode == False:
    print("This chip has no antibody spots. There are {} locations\n".format(spot_counter))
else:
    print("There are {} antibody spots\n".format(spot_counter))

pix_per_um = mag / cam_micron_per_pix
conv_factor = (cam_micron_per_pix / mag)**2

sample_name = vpipes.sample_namer(iris_path)

# virago_dir = '{}/v2results/{}'.format('/'.join(iris_path.split('/')[:-1]), chip_name)
virago_dir = '{}/v-analysis'.format(iris_path)
vcount_dir = '{}/vcounts'.format(virago_dir)
img_dir = '{}/processed_images'.format(virago_dir)
histo_dir = '{}/histograms'.format(virago_dir)
overlay_dir = '{}/overlays'.format(virago_dir)
filo_dir = '{}/filo'.format(virago_dir)
fluor_dir = '{}/fluor'.format(virago_dir)


if not os.path.exists(virago_dir):
    os.makedirs(virago_dir)
    made_dir = True
if not os.path.exists(img_dir): os.makedirs(img_dir)
if not os.path.exists(histo_dir): os.makedirs(histo_dir)
if not os.path.exists(fluor_dir): os.makedirs(fluor_dir)
if not os.path.exists(filo_dir): os.makedirs(filo_dir)
if not os.path.exists(vcount_dir): os.makedirs(vcount_dir)

else:
    os.chdir(vcount_dir)
    vdata_list = sorted(glob.glob(chip_name +'*.vdata.txt'))
    made_dir = False

#*********************************************************************************************#
# Text file Parser
#*********************************************************************************************#
os.chdir(iris_path)

spot_list = [int(file[1]) for file in txtcheck if (len(file) > 2) and (file[2].isalpha())]

pass_counter = int(max([imgfile.split(".")[2] for imgfile in image_list]))##Important
if pass_counter > 3: timeseries_mode = 'time'
else: timeseries_mode = 'scan'

scanned_spots = set(np.arange(1,spot_counter+1,1))
missing_spots = tuple(scanned_spots.difference(spot_list))
for val in missing_spots:
    iris_txt.insert(val-1,val)

spot_df = pd.DataFrame()
for ix, txtfile in enumerate(iris_txt):
    spot_data_solo = pd.DataFrame({'spot_number'   : [ix+1] * pass_counter,
                                   'scan_number'   : range(1,pass_counter + 1),
                                   'spot_type'     : [mAb_dict[ix+1][0]]*pass_counter,
                                   'chip_coords_xy': [mAb_dict[ix+1][1:3]]*pass_counter
                                   }
    )
    if not type(txtfile) is str:
        print("Missing text file for spot {}\n".format(txtfile))
        spot_data_solo['scan_time'] = [0] * pass_counter
        expt_date = None

    else:
        txtdata = pd.read_table(txtfile, sep = ':', error_bad_lines = False,
                            header = None, index_col = 0, usecols = [0, 1])
        expt_date = txtdata.loc['experiment_start'][1].split(" ")[0]

        pass_labels = [row for row in txtdata.index if row.startswith('pass_time')]
        times_s = txtdata.loc[pass_labels].values.flatten().astype(np.float)
        pass_diff = pass_counter - len(pass_labels)
        if pass_diff > 0: times_s = np.append(times_s, [0] * pass_diff)
        spot_data_solo['scan_time'] = np.round(times_s * 0.0167,2)
        print('File scanned:  {}'.format(txtfile))

    spot_df = spot_df.append(spot_data_solo, ignore_index = True)

#*********************************************************************************************#
# Image Scanning
spot_to_scan = 1
#*********************************************************************************************#
if (image_set != set()):

    if made_dir == True: image_toggle = 'yes'
    else: image_toggle = ''

    toggle_list = [str(i) for i in spot_list]
    toggle_list.extend(['yes', 'y', 'no', 'n'])
    while image_toggle not in (toggle_list):
        image_toggle = input("\nImage files detected. Do you want scan them for particles? (y/n)\n"
                           + "WARNING: This will take a long time!\n")
else:
    image_toggle = 'no'

if image_toggle.lower() not in ('no', 'n'):
    if image_toggle.isdigit():
        spot_to_scan = int(image_toggle)
    startTime = datetime.now()
    circle_dict, shift_dict, rotation_dict, marker_dict, overlay_dict = {},{},{},{},{}

    while spot_to_scan <= spot_counter:

        pps_list = sorted([file for file in image_set if int(file.split(".")[1]) == spot_to_scan])
        passes_per_spot = len(pps_list)
        spot_ID = '{}.{}'.format(chip_name, vpipes.three_digs(spot_to_scan))
        scans_counted = [int(file.split(".")[2]) for file in pps_list]
        if (passes_per_spot != pass_counter):
            print("Missing pgm files... fixing...\n")

            scan_set = set(range(1,pass_counter+1))

            missing_csvs = scan_set.difference(scans_counted)

            for scan in missing_csvs:
                vpipes.bad_data_writer(chip_name, spot_to_scan, scan, marker_dict, vcount_dir)

        total_shape_df = pd.DataFrame()

        for scan in range(0,passes_per_spot,1):
            first_scan = min(scans_counted)
            stack_list = [file for file in image_list if file.startswith(pps_list[scan])]
            top_img = stack_list[0]
            if top_img.split('.')[-1] == 'tif': tiff_toggle = True
            else: tiff_toggle = False
            validity = True

            fluor_files = [file for file in stack_list if file.split(".")[-2] in 'ABC']
            if fluor_files:
                stack_list = [file for file in stack_list if file not in fluor_files]
                print("\nFluorescent channel(s) detected: {}\n".format(fluor_files))

            spot_num, pass_num = map(int,top_img.split(".")[1:3])

            spot_type = mAb_dict[spot_num][0].split("(")[-1].strip(")")

            spot_pass_str = '{}.{}'.format(vpipes.three_digs(spot_num), vpipes.three_digs(pass_num))
            img_name = '.'.join([chip_name, spot_pass_str])

            if tiff_toggle == True:
                pic3D = skio.imread(top_img)
            else:
                scan_collection = skio.imread_collection(stack_list)
                pic3D = np.array([pic for pic in scan_collection], dtype='uint16')
                if convert_tiff == True:
                    vpipes.pgm_to_tiff(pic3D, img_name, stack_list,
                                       tiff_compression=1, archive_pgm=True)

            pic3D_orig = pic3D.copy()

            zslice_count, nrows, ncols = pic3D.shape

            if mirror.size == pic3D[0].size:
                pic3D = pic3D / mirror
                print("Applying mirror to image stack...\n")

            pic3D_norm = pic3D / (np.median(pic3D) * 2)

            pic3D_norm[pic3D_norm > 1] = 1

            pic3D_clahe = vimage.clahe_3D(pic3D_norm, cliplim=cliplim)##UserWarning silenced

            pic3D_rescale = vimage.rescale_3D(pic3D_clahe, perc_range=(perc_range))
            # vimage.gen_img(pic3D_rescale[9])
            print("Contrast adjusted\n")

            if pass_num == 1:
                marker = IRISmarker
                # found_markers = []
            else:
                marker = found_markers

            marker_locs, marker_mask, found_markers = vimage.marker_finder(image = pic3D_norm[0],
                                               marker = marker,
                                               thresh = 0.65,
                                               gen_mask = True,
            )
            # for marker in found_markers:
            #     vimage.gen_img(marker)
            marker_dict[spot_pass_str] = marker_locs

            pos_plane_list = []
            if (exo_toggle == True):

                for loc in marker_locs:

                    if (loc[0] < hmarker_h) or (loc[1] < hmarker_w):
                        pass

                    else:
                        marker3D_img = pic3D_norm[:,
                                                  loc[0]-hmarker_h : loc[0]+hmarker_h,
                                                  loc[1]-hmarker_w : loc[1]+hmarker_w
                        ]

                        teng_vals = [np.mean(sobel_h(img)**2 + sobel_v(img)**2) for img in marker3D_img]
                        min_plane = teng_vals.index(min(teng_vals))
                        pos_vals = teng_vals[:min_plane]
                        if not pos_vals == []:
                            pos_plane_list.append(teng_vals.index(max(pos_vals)))

                        neg_vals = teng_vals[min_plane:]
                        neg_vals_diff = list(np.diff(neg_vals))
                        neg_plane_list = [neg_vals_diff.index(val) for val in neg_vals_diff if val < 0]

                        if not neg_plane_list == []:
                            neg_plane = min(neg_plane_list) + min_plane
                        else:
                            neg_plane = neg_vals_diff.index(min(neg_vals_diff)) + min_plane


                        # plt.plot(range(1,zslice_count+1), teng_vals)
                    # teng_max = min(teng_vals.index(max(teng_vals))

            if not pos_plane_list == []:
                pos_plane = max(pos_plane_list)
            else:
                pos_plane = 6
                neg_plane = -1



            # def tenengrad(pic3D):
            #   z, nrows, ncols = pic3D.shape
                # pic3D_center = pic3D[:,(nrows//2-100):(nrows//2+100),(ncols//2-100):(ncols//2+100)]

            #     laplace_sum = sum(laplace_vals)
            #     laplace_vals_norm = [val/laplace_sum for val in laplace_vals]
            #     teng_diff = list(np.diff(teng_vals))
            #     laplace_diff = list(np.diff(laplace_vals))
            #     teng_sign = []
            #     # for val in teng_diff:
            #     #     if val < 0:
            #     #         teng_sign.append('Neg')
            #     #     elif val > 0:
            #     #         teng_sign.append('Pos')
            #     #     else:
            #     #         teng_sign.append(None)
            #     print(teng_sign)
            #     print(teng_diff.index(min(teng_diff))+1)
            #     print(laplace_diff.index(min(laplace_diff))+1)
            #     plt.plot(teng_vals_norm)
            #     plt.plot(laplace_vals_norm)
            #     plt.show()
            #     plt.clf()





            # find_focus(pic3D_rescale)

            pic_rescale_pos = pic3D_rescale[pos_plane]
            print("Using image {} from stack\n".format(vpipes.three_digs(pos_plane + 1)))

            pic_maxmin = np.max(pic3D_rescale, axis = 0) - np.min(pic3D_rescale, axis = 0)

            # pic3D_rescale_posneg = pic3D_rescale[pos_plane:neg_plane]
            # pic_stdproj = np.std(pic3D_rescale_posneg, axis=0)



            # vimage.image_details(pic3D_norm[9],pic3D_clahe[9],pic3D_rescale[9],pic_canny)



            # img_rotation = vimage.measure_rotation(marker_dict, spot_pass_str)
            # rotation_dict[spot_pass_str] = img_rotation

            if pass_counter <= 10: overlay_mode = 'series'
            else: overlay_mode = 'baseline'

            mean_shift, overlay_toggle = vimage.measure_shift(marker_dict, pass_num,
                                                              spot_num, mode = overlay_mode
            )
            shift_dict[spot_pass_str] = mean_shift


            if (overlay_toggle == True):# & (finish_anal not in ('yes', 'y')):
                print("Valid Shift\n")
                # img_overlay = vimage.overlayer(overlay_dict, overlay_toggle, spot_num, pass_num,
                #                                 mean_shift, mode = overlay_mode)
                # if img_overlay is not None:
                #     overlay_name = "{}_overlay_{}".format(img_name, overlay_mode)
                #     vimage.gen_img(img_overlay,
                #                    name = overlay_name,
                #                    savedir = overlay_dir,
                #                    show = False)
            elif (overlay_toggle == False) & (pass_num != first_scan):
                validity = False
            elif pass_num == first_scan:
                print("First Valid Scan\n")
            else:
                print("Cannot overlay images\n")

            if spot_num in circle_dict:
                spot_coords = circle_dict[spot_num]
                shift_x = spot_coords[0] + mean_shift[1]
                shift_y = spot_coords[1] + mean_shift[0]
                spot_coords = (shift_x, shift_y, spot_coords[2])
                circle_dict[spot_num] = spot_coords
            else:
                pic_canny = canny(pic_maxmin, sigma = canny_sig)
                # vimage.gen_img(pic_canny)
                spot_coords = vimage.spot_finder(pic_canny,
                                                 rad_range=(325,601),
                                                 Ab_spot=Ab_spot_mode
                )

                circle_dict[spot_num] = spot_coords

            row, col = np.ogrid[:nrows,:ncols]
            width = col - spot_coords[0]
            height = row - spot_coords[1]
            rad = spot_coords[2] - 25
            disk_mask = (width**2 + height**2 > rad**2)
            full_mask = disk_mask + marker_mask

            pic_maxmin_masked = np.ma.array(pic_maxmin,
                                            mask = full_mask).filled(fill_value = np.nan)
            pic_rescale_pos_ma = np.ma.array(pic_rescale_pos,
                                            mask = full_mask).filled(fill_value = np.nan)
#*********************************************************************************************#
            if pass_num > first_scan:
                particle_mask = vimage.particle_mask_shift(particle_mask, mean_shift)


            pic_to_show = pic_rescale_pos



#*********************************************************************************************#
            with warnings.catch_warnings():
                ##RuntimeWarning ignored: invalid values are expected
                warnings.simplefilter("ignore")
                warnings.warn(RuntimeWarning)

                shapedex = shape_index(pic_rescale_pos)
                shapedex = np.ma.array(shapedex,mask = full_mask).filled(fill_value = np.nan)

                if pass_num > first_scan:

                    shapedex = np.ma.array(shapedex,mask = particle_mask).filled(fill_value = -1)

            pix_area = np.count_nonzero(np.invert(np.isnan(shapedex)))

            area_sqmm = round((pix_area * conv_factor) * 1e-6, 6)

            vdata_dict = {'img_name'        : img_name,
                          'spot_type'       : spot_type,
                          'area_sqmm'       : area_sqmm,
                          'mean_shift'      : mean_shift,
                          'overlay_mode'    : overlay_mode,
                          'total_particles' : 0,
                          'pos_plane'       : pos_plane,
                          'exo_toggle'      : exo_toggle,
                          'spot_coords'     : spot_coords,
                          'marker_locs'     : marker_locs,
                          'validity'        : validity,
                          'version'         : version
            }
            maxmin_median = np.nanmedian(pic_maxmin_masked)

            print("Median intensity of spot = {}\n".format(round(maxmin_median,4)))

            if Ab_spot_mode == False:
                maxmin_median = 0.3
                print("Adjusted median intensity of spot = {}\n".format(round(maxmin_median,4)))

            ridge = 0.5
            sphere = 1
            # if Ab_spot_mode == True:
            ridge_thresh = maxmin_median*4
            sphere_thresh = maxmin_median*2
            ridge_thresh_s = maxmin_median*3



            ridge_list = vquant.classify_shape(shapedex, pic_maxmin, ridge,
                                               delta=0.25, intensity=ridge_thresh
            )
            sphere_list = vquant.classify_shape(shapedex, pic_maxmin, sphere,
                                                delta=0.2, intensity=sphere_thresh
            )
            ridge_list_s = vquant.classify_shape(ndi.gaussian_filter(shapedex, sigma=1),
                                                 pic_maxmin, ridge,
                                                 delta=0.3, intensity=ridge_thresh_s
            )


            pix_list = ridge_list + sphere_list
            ridge_list_s = [coord for coord in ridge_list_s if coord not in pix_list]
            pix_list = pix_list + ridge_list_s

            # raise NameError


            pic_binary = np.zeros_like(pic_maxmin, dtype=int)
            for coord in pix_list:
                if pic_binary[coord] == 0: pic_binary[coord] = 1

            pic_binary = ndi.morphology.binary_fill_holes(pic_binary)

            if pass_num == first_scan:
                particle_mask = ndi.morphology.binary_dilation(pic_binary, iterations=3)

            else:
                particle_mask = np.add(particle_mask,
                                       ndi.morphology.binary_dilation(pic_binary, iterations=2)
                )

#*********************************************************************************************#
            ##EXTRACT DATA FROM THE BINARY IMAGE
            binary_props = regionprops(label(pic_binary, connectivity = 2),
                                       pic3D[pos_plane], cache = True
            )

            with warnings.catch_warnings():
                ##UserWarning ignored
                warnings.simplefilter("ignore")
                warnings.warn(UserWarning)
                shape_df = pd.DataFrame([[region.label,
                                          [tuple(coords) for coords in region.coords],
                                          region.centroid,
                                          (region.bbox[0:2], region.bbox[2:]),
                                          region.area,
                                          region.perimeter,
                                          region.major_axis_length,
                                          region.minor_axis_length]
                                          for region in binary_props
                                          if (region.area > 3) & (region.area <= 300)],
                                          columns=['label_bin','coords','centroid','bbox',
                                                   'area','perim','maj_ax','min_ax']
                )

            if not shape_df.empty:
                shape_df['pass_number'] = [pass_num]*len(shape_df.index)
                shape_df['perim_area_ratio']= list(map(lambda A,P: (P**2) / (4*np.pi * A),
                                                        shape_df.area, shape_df.perim)
                )
                shape_df['elongation'] = shape_df.maj_ax / shape_df.min_ax
                shape_df['bbox_verts'] = [np.array([(bbox[0][0] - 2, bbox[0][1] - 2),
                                                    (bbox[0][0] - 2, bbox[1][1] + 2),
                                                    (bbox[1][0] + 2, bbox[1][1] + 2),
                                                    (bbox[1][0] + 2, bbox[0][1] - 2)])
                                           for bbox in shape_df.bbox
                ]
                shape_df.drop(columns=['bbox', 'perim', 'maj_ax', 'min_ax'], inplace=True)
            else:
                print("----No valid particle shapes----\n")
                print(shape_df)
                with open('{}/{}.vdata.txt'.format(vcount_dir,img_name),'w') as f:
                    for k,v in vdata_dict.items():
                        f.write('{}: {}\n'.format(k,v))

                vgraph.gen_particle_image(pic_to_show,shape_df,spot_coords,
                                          pix_per_um=pix_per_um, cv_cutoff=cv_cutoff,
                                          show_particles=False,
                                          scalebar=15, markers=marker_locs,
                                          exo_toggle=exo_toggle
                )
                plt.savefig('{}/{}.{}.png'.format(img_dir, img_name, spot_type), dpi = 96)
                plt.clf(); plt.close('all')
                print("#******************PNG generated for {}************************#".format(img_name))
                continue

#*********************************************************************************************#


            def measure_z_stack(z_stack, std_z_stack, a0=0.1, b0=0.1, c0=1, show = False):

                x_data = np.arange(0,len(z_stack))

                maxa, mina = max(z_stack), min(z_stack)
                max_z = z_stack.index(maxa)
                intensity = round(maxa - mina,5)

                basedex = (max_z + z_stack.index(mina)) // 2
                y_data = list(map(lambda x: x - z_stack[basedex], z_stack))


                try:
                    fit_params, params_cov = curve_fit(psf_sine, x_data, y_data,
                                                        sigma=std_z_stack,
                                                        p0=[a0, b0, c0],
                                                            # bounds=([0.05,0.3,1],[0.4,0.5,1.2]),
                                                        method='lm')
                except RuntimeError:
                    return 0, intensity, max_z


                y_fit = psf_sine(x_data,fit_params[0],fit_params[1],fit_params[2])

                ss_res = np.sum((y_data - y_fit)**2)
                ss_tot = np.sum((y_data - np.mean(y_data))**2)
                r2 = round(1 - (ss_res / ss_tot),5)

                if show == True:
                    plt.plot(y_fit)
                    plt.errorbar(x=x_data,y=y_data,yerr=std_z_stack, linestyle='--')
                    plt.text(x=0,y=0, s='R^2 = {0}; a,b,c = {1}'.format(r2,np.round(fit_params,4)))

                    plt.xlim(-5,25)
                    plt.show()

                return r2, intensity, max_z





            filo_pts_tot, round_pts_tot  = [],[]
            r2_list, greatest_max_list, max_z_list, intensity_list, z_stacks = [],[],[],[],[]

            for coord_array in shape_df.coords:
                coord_set = set(coord_array)
                filo_pts = len(coord_set.intersection(ridge_list))

                filo_pts = filo_pts + (len(coord_set.intersection(ridge_list_s)) * 0.15)

                round_pts = len(coord_set.intersection(sphere_list))

                filo_pts_tot.append(filo_pts)
                round_pts_tot.append(round_pts)

                # pix_max_list, z_list = vquant.measure_max_intensity_stack(pic3D, coord_array)

                # greatest_max.append(np.max(pix_max_list))
                # max_z.append(z_list[pix_max_list.index(max(pix_max_list))])
                all_z_stacks = np.array([list(pic3D_norm[:,coords[0],coords[1]])
                                                for coords in coord_array])
                greatest_max = np.max(all_z_stacks)
                max_z_stack = all_z_stacks[np.where(all_z_stacks == greatest_max)[0][0]].tolist()
                mean_z_stack = list(np.round(np.mean(all_z_stacks, axis=0),4))
                std_z_stack = list(np.round(np.std(all_z_stacks, axis=0),4))

                r2, intensity, max_z = measure_z_stack(mean_z_stack,std_z_stack, show=True)

                r2_list.append(r2)
                intensity_list.append(intensity)
                max_z_list.append(max_z)
                greatest_max_list.append(greatest_max)
                z_stacks.append(mean_z_stack)

            shape_df['intensity'] = intensity_list
            shape_df['max_z'] = max_z_list
            shape_df['greatest_max'] = greatest_max_list
            shape_df['z_stack'] = z_stacks
            shape_df['r2_corr'] = r2_list
            shape_df['filo_points'] = filo_pts_tot
            shape_df['round_points'] = round_pts_tot
            # raise Error
            # def measure_psf_corr(z_stacks, a0=0.1, b0=0.15, c0=1.2, show = False):
            #     # z_stacks = [list(pic3D[:, val[0], val[1]]) for val in pix_list]
            #     x_data = np.arange(0,len(z_stacks[0]))
            #     r2_list, intensity_list = [],[]
            #     for i,arr in enumerate(z_stacks):
            #         maxa, mina = max(arr), min(arr)
            #         intensity_list.append(round(maxa - mina,5))
            #         basedex = (arr.index(maxa) + arr.index(mina)) // 2
            #         y_data = list(map(lambda x: x - arr[basedex], arr))
            #
            #         try: fit_params, params_cov = curve_fit(psf_sine, x_data, y_data,
            #                                                 p0=[a0, b0, c0],
            #                                                 # bounds=([0.05,0.3,1],[0.4,0.5,1.2]),
            #                                                 method='lm')
            #         except RuntimeError:
            #             r2_list.append(0)
            #             continue
            #
            #         y_fit = psf_sine(x_data,fit_params[0],fit_params[1],fit_params[2])
            #
            #         ss_res = np.sum((y_data - y_fit)**2)
            #         ss_tot = np.sum((y_data - np.mean(y_data))**2)
            #         r_sq = round(1 - (ss_res / ss_tot),5)
            #         r2_list.append(r_sq)
            #
            #         if show == True:
            #             plt.plot(y_fit)
            #             plt.scatter(x=x_data,y=y_data)
            #             plt.text(x=0,y=0, s='R^2 = {}'.format(r_sq))
            #             plt.xlim(-5,25)
            #             plt.show()
            #
            #     return r2_list #pd.DataFrame({'coords':pix_list,'r2':r2_list,'intensity':intensity_list})
            #
            #
            # shape_df['r2_corr'] = measure_psf_corr(z_stacks, show = False)
            print("Done measuring corr\n")





            median_bg_list, cv_bg_list = [],[]

            for i, bbox in enumerate(shape_df['bbox_verts']):
                plane = shape_df['max_z'].loc[i]-1

                bbox[:,0][np.where(bbox[:,0] >= nrows)] = nrows - 1
                bbox[:,1][np.where(bbox[:,1] >= ncols)] = ncols - 1

                top_edge = pic3D[plane][bbox[0][0],bbox[0][1]:bbox[1][1]+1]
                bottom_edge = pic3D[plane][bbox[1][0]-1,bbox[0][1]:bbox[1][1]+1]
                rt_edge = pic3D[plane][bbox[0][0]:bbox[1][0]+1,bbox[1][1]]
                left_edge = pic3D[plane][bbox[0][0]:bbox[1][0]+1,bbox[0][1]]
                all_edges = np.hstack([top_edge, bottom_edge, rt_edge, left_edge])

                median_bg = np.median(all_edges)
                cv_bg = np.std(all_edges) / np.mean(all_edges)

                median_bg_list.append(median_bg)
                cv_bg_list.append(cv_bg)


            shape_df['median_bg'] = median_bg_list
            shape_df['cv_bg'] = cv_bg_list


            shape_df = shape_df[(shape_df['filo_points'] + shape_df['round_points']) >= 1]

            shape_df['perc_contrast'] = ((shape_df['greatest_max'] - shape_df['median_bg'])*100
                                                    / shape_df['median_bg']
            )
            shape_df = shape_df[(shape_df['filo_points'] + shape_df['round_points']) >= 1]

            shape_df['filo_score'] = ((shape_df['filo_points']/shape_df['area'])
                                     - (shape_df['round_points']/shape_df['area'])
            )

#---------------------------------------------------------------------------------------------#
            filo_df = shape_df[(shape_df.filo_score >= 0.25) & (shape_df.area > 10)].copy()


            filolen_df = pd.DataFrame([vquant.measure_filo_length(coords,pix_per_um) for coords in filo_df.coords],
                                       columns=['filo_lengths','vertices'], index=filo_df.index)


            shape_df = pd.concat([shape_df, filolen_df],axis=1)
#---------------------------------------------------------------------------------------------#
            ### Fluorescent File Processer WORK IN PRORGRESS
            #min_sig = 0.9; max_sig = 2; thresh = .12
#---------------------------------------------------------------------------------------------#
            if fluor_files:
                # channel_list = ['A','B','C']
                for fluor_filename in fluor_files:
                    fluor_img = skio.imread(fluor_filename)
                    if mirror.size == fluor_img.size:
                        fluor_img = fluor_img / mirror

                    fluor_rescale = vgraph.fluor_overlayer(fluor_img, pic_maxmin,
                                                           fluor_filename, savedir=fluor_dir
                    )

            if (show_filos == True):
                vgraph.filo_image_gen(shape_df, pic_rescale_pos, shapedex, pic_binary,
                                      ridge_list, sphere_list, ridge_list_s,
                                      cv_cutoff=cv_cutoff, r2_cutoff = r2_cutoff, show=True
                )
            # raise NameError
#*********************************************************************************************#
            valid_shape_df = shape_df[(shape_df['cv_bg'] < cv_cutoff) & (shape_df['r2_corr'] >= 0.9)]


#---------------------------------------------------------------------------------------------#

            total_particles = len(valid_shape_df.perc_contrast)
            kparticle_density = round(total_particles / area_sqmm * 0.001, 2)

            if pass_num != first_scan:
                print("Particle density in {}: {} kp/sq.mm\n".format(img_name, kparticle_density))
            else:
                print("Background density in {}: {} kp/sq.mm\n".format(img_name, kparticle_density))


            shape_df.reset_index(drop=True, inplace=True)

            total_shape_df = pd.concat([total_shape_df, shape_df], axis = 0)
            total_shape_df.reset_index(drop=True, inplace=True)
            # if (passes_per_spot > 1) & (pass_num == passes_per_spot) & (total_particles > 0):
                # filohisto(total_shape_df, filo_cutoff = 0.25, irreg_cutoff = -0.25, range=filohist_range)
                # plt.savefig('{}/{}.filohistogram.png'.format(filo_dir, img_name))
                # print("Filament histogram generated")

            vdata_dict.update({'total_particles': total_particles})

            with open('{}/{}.vdata.txt'.format(vcount_dir,img_name),'w') as f:
                for k,v in vdata_dict.items():
                    f.write('{}: {}\n'.format(k,v))


#---------------------------------------------------------------------------------------------#
        ####Processed Image Renderer
            vgraph.gen_particle_image(pic_to_show,total_shape_df,spot_coords,
                                      pix_per_um=pix_per_um,
                                      cv_cutoff=cv_cutoff,
                                      r2_cutoff=r2_cutoff,
                                      show_particles=show_particles,
                                      scalebar=15, markers=marker_locs,
                                      exo_toggle=exo_toggle
            )

            # plt.show()
            plt.savefig('{}/{}.{}.png'.format(img_dir, img_name, spot_type), dpi = 96)
            plt.clf(); plt.close('all')
            print("#******************PNG generated for {}************************#".format(img_name))
            if not shape_df.empty:
                vgraph.intensity_profile_graph(shape_df, pass_num, zslice_count,
                                               vcount_dir, exo_toggle, img_name
                )

#---------------------------------------------------------------------------------------------#
        total_shape_df.to_csv('{}/{}.particle_data.csv'.format(vcount_dir, spot_ID))
        analysis_time = str(datetime.now() - startTime)

        spot_to_scan += 1
        print("Time to scan images: {}".format(analysis_time))
#*********************************************************************************************#
    info_dict = {'chip_name'      : chip_name,
                 'sample_info'    : sample_name,
                 'spot_number'    : spot_counter,
                 'total_passes'   : pass_counter,
                 'experiment_date': expt_date,
                 'analysis_time'  : analysis_time,
                 'version'        : version
    }
    with open('{}/{}.expt_info_{}.txt'.format(virago_dir,chip_name,version),'w') as info_file:
        for k,v in info_dict.items():
            info_file.write('{}: {}\n'.format(k,v))
#*********************************************************************************************#
os.chdir(virago_dir)
info_list = sorted(glob.glob('*_info_*'))
if info_list == []:
    print("No valid data to interpret. Exiting...")
    sys.exit()
else:
    version_list = ['.'.join(file.split('_')[-1].split('.')[:3]) for file in info_list]
    version = max(version_list, key=vpipes.version_finder)
    print("\nData from version {}\n".format(version))

os.chdir(vcount_dir)
particle_data_list = sorted(glob.glob(chip_name +'*.particle_data.csv'))
vdata_list = sorted(glob.glob(chip_name +'*.vdata.txt'))

if len(vdata_list) >= (len(iris_txt) * pass_counter):
    cont_str = str(input("\nEnter the minimum and maximum percent intensity values,"
                                + " separated by a dash.\n"))
    while "-" not in cont_str:
        cont_str = str(input("\nPlease enter two values separated by a dash.\n"))
    else:
        min_cont, max_cont = map(float, cont_str.split("-"))

    cont_window = [min_cont, max_cont]

    vdata_dict ={}
    for vfile in vdata_list:
        vdata_dict = vquant.vdata_reader(vfile, vdata_dict, prop_list=['area_sqmm'])

    spot_df['area'] = vdata_dict['area_sqmm']
    spot_df['validity'] = vdata_dict['validity']


    particle_counts, filo_counts,irreg_counts = [],[],[]
    histogram_dict = {}



    new_particle_count, cum_particle_count = [],[]
    for i, csvfile in enumerate(particle_data_list):
        particle_df = pd.read_csv(csvfile, error_bad_lines=False, header=0, index_col=0)
        if not particle_df.empty:
            # pc_series = combo_df.perc_contrast#[  #(combo_df.perc_contrast > min_cont)
                                            #        (combo_df.perc_contrast <= max_cont)
                                            #        & (combo_df.cv_bg < cv_cutoff)
        #    ]
            cumulative_particles = 0
            for j in range(1,pass_counter+1):

                area_str = spot_df.area[  (spot_df.spot_number == i+1)
                                        & (spot_df.scan_number == j)].values[0]
                area_squm = int(float(area_str)*1e6)

                protohisto_series = particle_df.perc_contrast[(particle_df.pass_number == j)
                                                             &(particle_df.perc_contrast <= max_cont)
                                                             &(particle_df.cv_bg < cv_cutoff)
                ]

                csv_id = '{}.{}.{}'.format(csvfile.split(".")[1], vpipes.three_digs(j), area_squm)
                histogram_dict[csv_id] = list(protohisto_series)
                fin_particle_series = protohisto_series[protohisto_series > min_cont]

                particles_per_pass = len(fin_particle_series)
                new_particle_count.append(particles_per_pass)
                cumulative_particles += particles_per_pass
                cum_particle_count.append(cumulative_particles)

                print(  'File scanned: {}; '.format(csvfile)
                      + 'Scan {}, '.format(j)
                      + 'Particles accumulated: {}'.format(cumulative_particles)
                )
        else:
            print("Missing data for {}\n".format(csvfile))
            new_particle_count = new_particle_count + ([0]*pass_counter)
            cum_particle_count = cum_particle_count + ([0]*pass_counter)


    spot_df['new_particles'] = new_particle_count
    spot_df['cumulative_particles'] = cum_particle_count
    spot_df['kparticle_density'] = np.round(cum_particle_count
                                            / spot_df.area.astype(float) * 0.001, 3
    )

    spot_df.loc[spot_df.kparticle_density == 0, 'valid'] = False

    spot_df['normalized_density'] = vquant.density_normalizer(spot_df, spot_counter)

    os.chdir(iris_path)

elif len(vdata_list) != (len(iris_txt) * pass_counter):
    print("Missing VIRAGO analysis files\n")
    sys.exit()

spot_df, histogram_dict = vquant.spot_remover(spot_df, histogram_dict,
                                              vdata_list, vcount_dir,
                                              iris_path, quarantine_img=False
)

vhf_colormap = ('#e41a1c',
                '#377eb8',
                '#4daf4a',
                '#984ea3',
                '#ff7f00',
                '#cccc00',
                '#a65628',
                '#f781bf',
                'gray',
                'black',
                '#a6cee3',
                '#1f78b4',
                '#b2df8a',
                '#33a02c',
                '#fb9a99',
                '#e31a1c',
                '#fdbf6f',
                '#ff7f00',
                '#cab2d6',
                '#6a3d9a',
                '#ffff99',
                '#b15928',
)


#*********************************************************************************************#
##HISTOGRAM CODE
if (pass_counter > 1):# &(min_cont == 0):
    raw_histogram_df = vgraph.histogrammer(histogram_dict, spot_counter, cont_window)
    raw_histogram_df.to_csv('{}/{}_raw_histogram_data.v{}.csv'.format(histo_dir, chip_name, version))

    sum_histogram_df = vgraph.sum_histogram(raw_histogram_df, spot_counter, pass_counter)
    sum_histogram_df.to_csv('{}/{}.sum_histogram_data.v{}.csv'.format(histo_dir, chip_name, version))

    avg_histogram_df = vgraph.average_histogram(sum_histogram_df, spot_df, pass_counter)
    avg_histogram_df.to_csv('{}/{}_avg_histogram_data.v{}.csv'.format(histo_dir, chip_name, version))
#*********************************************************************************************#
    """Generates a histogram figure for each pass in the IRIS experiment from a
    DataFrame representing the average data for every spot type"""

    bin_array = np.array(avg_histogram_df.pop('bins'))
    smooth_histo_df = avg_histogram_df.filter(regex='rollingmean').rename(columns=lambda x: x[:-12])
    sdm_histo_df = avg_histogram_df.filter(regex='sdm').rename(columns=lambda x: x[:-4])
    smooth_max = np.max(np.max(smooth_histo_df))
    sdm_max = np.max(np.max(sdm_histo_df))
    if np.isnan(sdm_max): sdm_max = 0
    # histo_min = int(np.min(np.min(avg_histogram_df)))
    histo_max = np.round(smooth_max+sdm_max,2)

    y_grid = np.round(histo_max / 10,2)
    if pass_counter < 10: passes_to_show = 1
    else: passes_to_show = pass_counter // 10
    line_settings = dict(lw=2 ,alpha=0.75)
    for i in range(2, pass_counter+1, passes_to_show):
        sns.set(style='ticks')
        c = 0
        for j, col in enumerate(smooth_histo_df):
            splitcol = col.split("_")
            if len(splitcol) == 2:
                spot_type, pass_num = splitcol
            else:
                spot_type, pass_num = splitcol[::2]
            pass_num = int(pass_num)
            if pass_num == i:
                plt.errorbar(bin_array,
                         smooth_histo_df[col],
                         yerr=sdm_histo_df[col],
                         color = vhf_colormap[c],
                         label = spot_type,
                         elinewidth = 0.5,
                         **line_settings
                )
                c += 1

        plt.title(chip_name+" Pass "+str(i)+" Average Histograms")
        plt.axhline(y=0, ls='dotted', c='k', alpha=0.75)
        plt.axvline(x=min_cont, ls='dashed',c='k',alpha=0.8)

        if len(mAb_dict_rev.keys()) <= 8: plt.legend(loc = 'best', fontsize = 14)
        else: plt.legend(loc = 'best', fontsize = 8)

        plt.ylabel("Frequency (kparticles/mm" + r'$^2$'+")", size = 14)

        plt.yticks(np.arange(0, histo_max, y_grid), size = 12)
        plt.xlabel("Contrast (%)", size = 14)

        xgrid = len(bin_array) // 10
        xlabels = np.append(bin_array, max_cont)[::xgrid]
        plt.xticks(xlabels, size = 12, rotation = 90)



        figname = ('{}_combohisto_pass_{}_contrast_{}.png'.format(chip_name,i,cont_str))
        plt.savefig('{}/{}'.format(histo_dir,figname), bbox_inches = 'tight')#, dpi = 150)
        print("File generated: {}".format(figname))
        plt.clf()


normalized_density = vquant.density_normalizer(spot_df, spot_counter)

spot_df['normalized_density'] = normalized_density


averaged_df = vgraph.average_spot_data(spot_df, pass_counter)

if pass_counter > 2:
    vgraph.generate_timeseries(spot_df, averaged_df, cont_window, mAb_dict,
                                chip_name, sample_name, vhf_colormap, version,
                                scan_or_time = timeseries_mode, baseline = True,
                                savedir = virago_dir
    )
elif pass_counter <= 2:
    vgraph.generate_barplot(spot_df, pass_counter, cont_window,
                            chip_name, sample_name, vhf_colormap, version,
                            plot_3sigma=True, savedir=virago_dir
    )

vgraph.chipArray_graph(spot_df, vhf_colormap,
                      chip_name=chip_name, sample_name=sample_name, cont_str=cont_str,
                      exo_toggle=exo_toggle, savedir=virago_dir, version=version
)

spot_df_name='{}/{}_spot_data.{}contrast.v{}.csv'.format(virago_dir, chip_name,
                                                         cont_str, version
)
spot_df.to_csv(spot_df_name)
print('File generated: {}'.format(spot_df_name))
