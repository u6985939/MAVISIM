import pytest
from mavisim import ImageGenerator, Source
import numpy as np
import astropy.io.fits as fits
import tests.test_parameters as input_par
from importlib import reload

GAUSS_PSF = "tests/test_psf_gauss.fits"
E2E_PSF = "tests/test_psf_e2e.fits"


def make_source(n_sources=1):
    """Create a source table from the test_parameters file

    Returns:
        src : (mavisim.Source) source object
    """
    reload(input_par)
    for _ in range(n_sources - 1):
        input_par.input_cat.add_row(input_par.input_cat[0])
    exp_time = 10
    src = Source(input_par=input_par, exp_time=exp_time, static_dist=False)
    src.build_source()
    return src


def make_image(width=8000, padding=1000, rebin=2):
    """Create an image from the test source object and some default parameters

    Returns:
        im : (np.ndarray) image generated by mavisim
        src: (mavisim.Source) source object used to generate image
    """
    src = make_source()
    pixsize = 3.75e-3
    image_gen = ImageGenerator(array_width_pix=width + 2 * padding, source=src,
                               psfs_file=GAUSS_PSF, pixsize=pixsize,
                               gauss_width_pix=34, which_psf=0, norm_psf=True)
    image_gen.main()
    im = image_gen.get_rebinned_cropped(rebin_factor=rebin, cropped_width_as=width * pixsize)
    return im, src


def get_psf_cog(filename):
    """take a PSF from a fits file and return its centroid

    Returns:
        cog: (np.ndarray) (2,) array containing CoG in x and y, in pixel units
    """
    psf = fits.open(filename)[1].data
    cog = get_cog(psf)
    return cog


def get_cog(image):
    """returns the centre of gravity of an image in pixel units, here is where
    we define the coordinates of all subsequent operations. By convention, we
    propose that the (0,0) coordinate is in the absolute centre of the image.

    For example, a symmetric source placed at (0,0) pixels in an square image
    with an even number of pixels in each dimension (e.g., 4000x4000 pixels)
    will have uniform intensity across the 2x2 sub grid of pixels in the centre
    of the image. In numpy conventions, this is to say that:
        image.shape = (4000,4000)
        i = image[1999,1999]
        assert image[1999,2000] == i
        assert image[2000,1999] == i
        assert image[2000,2000] == i
        s = image[:2000,:2000].sum()
        assert image[2000:,:2000].sum() == s
        assert image[:2000,2000:].sum() == s
        assert image[2000:,2000:].sum() == s

    If the image were to have an odd number of pixels in each dimension (e.g., 3x3),
    then a symmetric object placed at (0,0) pixels should fall "in the centre" of the
    central pixel, and the 4 adjacent pixels (directly above,below,left,right of the
    centre) should have equal intensities to each other.

    This definition is consistent with the philosophy that pixels are "bins" of the
    continuous space, rather than discrete samples of the continuous space. So the
    full width of the image corresponds to exactly the number of pixels along the x
    dimension (N) multiplied by the pixel scale. Conversely, in the discrete sampling
    philosophy, there is a fencepost issue where the full width of the image is N-1
    multiplied by the pixel scale. This is a subtle difference but we're dealing with
    sub-pixel astrometry so it seems important to get this right.
    """
    yy, xx = np.mgrid[:image.shape[0], :image.shape[1]].astype(np.float64)
    yy -= image.shape[0] / 2  # centering the coordinates
    yy += 0.5  # offset to achieve desired convention
    xx -= image.shape[1] / 2  # centering the coordinates
    xx += 0.5  # offset to achieve desired convention
    im_sum = image.sum()
    cog_x = (image * xx).sum() / im_sum
    cog_y = (image * yy).sum() / im_sum
    return np.array([cog_x, cog_y])


def get_cog_windowed(im: np.ndarray, offset_x: int, offset_y: int, width: int):
    """Crop a large image to a smaller region and return the cog in the large image
    coordinates

    Arguments:
        im : (np.ndarray) full size square 2d array to be cog'd
        offset_x : (int) offset in x (axis=1) to start the cropping of the image
        offset_y : (int) same but in y (axis=0)
        width : (int) width of region to crop

    Returns:
        cog : (np.ndarray) (2,) array containing x and y CoG values
    """
    cog = get_cog(im[offset_y:offset_y + width, offset_x:offset_x + width])
    cog = cog + np.array([offset_x, offset_y]) + width / 2 - im.shape[0] / 2
    return cog


def test_make_image():
    """Test the image maker runs without errors and produces the expected shape image
    """
    im, _ = make_image(width=8000, padding=1000, rebin=2)
    assert im.shape[0] == 4000
    assert im.shape[1] == 4000

    im, _ = make_image(width=2000, padding=100, rebin=1)
    assert im.shape[0] == 2000
    assert im.shape[1] == 2000


def test_photometry():
    """Verify that flux is conserved from source table to final image
    """
    im, src = make_image()
    assert np.abs((im.sum() - src.flux.sum()) / src.flux.sum()) < 0.001  # make sure less than 0.1% flux error per star


def test_cog_convention():
    """Verify that cog of an even and odd shape image produces the expected position
    """
    # even
    # central source
    im = np.array([
        [0, 0, 0, 0],
        [0, 7, 7, 0],
        [0, 7, 7, 0],
        [0, 0, 0, 0]
    ]).astype(np.float64)
    assert np.allclose(get_cog(im), np.array([0, 0]))
    # pos x-shifted source
    im = np.array([
        [0, 0, 0, 0],
        [0, 0, 2, 2],
        [0, 0, 2, 2],
        [0, 0, 0, 0]
    ]).astype(np.float64)
    assert np.allclose(get_cog(im), np.array([1, 0]))

    # odd
    # central source
    im = np.array([
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
        [0, 0, 1, 0, 0],
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0]
    ]).astype(np.float64)
    assert np.allclose(get_cog(im), np.array([0, 0]))
    # neg y-shifted source
    im = np.array([
        [0, 0, 9, 0, 0],
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0]
    ]).astype(np.float64)
    assert np.allclose(get_cog(im), np.array([0, -2]))


def test_init_pos_is_zero():
    """Verify that the default source object has a position of zero, since
    that is what should be specified in the source table.
    """
    im, _ = make_image()
    cog = get_cog(im)
    assert np.allclose(cog, np.array([0, 0]))


def get_gr_distributed_sources(npoints):
    """Create a set of source coordinates on the unit disc to be used for pseudo-randomly
    distributing test sources. The furthest point from the centre lies just inside the unit
    disc.

    Uses a set of points distributed by the golden ratio to try and avoid repetative pixel
    sampling and pass tests with a hidden bug.

    Returns:
        pos : (np.ndarray) (npoints,2) array of coordinates [[x1,y1],[x2,y2],...,[xnpoints,ynpoints]]
    """
    gr_theta = (3 - 5**0.5) * np.pi
    radius = (np.arange(npoints) / npoints)**0.5
    theta = (np.arange(npoints) * gr_theta)
    pos = np.array([radius * np.cos(theta), radius * np.sin(theta)]).T
    return pos


def test_psf_cog():
    """PSFs should be saved so that the average tip/tilt in the phase space has
    an expectation of zero, which corresponds to a shift of half a pixel with respect
    to the coordinate definition used elsewhere. This appears to be the default
    convention used in most AO simulation software.
    """
    psf_cog = get_psf_cog(GAUSS_PSF)
    assert np.allclose(psf_cog, np.array([0.5, 0.5]))


@pytest.mark.parametrize("psf_file,tolerance,rebin", [
    (GAUSS_PSF, 1e-7, 1),  # gaussian PSFs can tolerate a much higher precision
    (GAUSS_PSF, 1e-7, 2),
    (GAUSS_PSF, 1e-7, 4),
    (E2E_PSF, 1e-2, 1),  # e2e psfs have non-zero strength all the way to the edges
    (E2E_PSF, 1e-2, 2),  # so classical CoG algorithms are not perfect.
    (E2E_PSF, 1e-2, 4),
])
def test_astrometry(psf_file, tolerance, rebin):
    """Verify that an image with a single source can have its position
    recovered to a desired accuracy.

    This function works by generating many images with floating point positioned
    sources and performing a CoG over the entire image. If the image is oversampled,
    not truncated, and noiseless, this should be exactly the right value (from uuu
    Fourier transform theory). Gaussian PSFs behave this way, but e2e PSFs aren't
    perfectly zero for any window size, probably due to the finite precision FFT
    computations performed to make them. The Gaussian PSF is made directly in the
    image space so is truly zero at some distance from the centre.
    """
    psf_cog = get_psf_cog(psf_file) - np.array([0.5, 0.5])

    # make image and check cog
    src = make_source()
    err_xl = []
    err_yl = []
    max_rad = 5.0  # arcsec
    pixsize = 3.75e-3  # arcsec
    npoints = 10
    pos = max_rad * get_gr_distributed_sources(npoints)
    for new_pos in pos:
        src.gauss_pos[:] = new_pos.copy()
        image_gen = ImageGenerator(array_width_pix=5000, source=src, psfs_file=psf_file,
                                   pixsize=pixsize, gauss_width_pix=32, which_psf=0, norm_psf=True)
        image_gen.main()
        im = image_gen.get_rebinned_cropped(rebin_factor=rebin, cropped_width_as=15)
        cog_x, cog_y = get_cog(im)
        # measure error in pixels:
        err_xl.append(cog_x * rebin - new_pos[0] / pixsize - psf_cog[0])
        err_yl.append(cog_y * rebin - new_pos[1] / pixsize - psf_cog[1])
    err_x = np.array(err_xl)
    err_y = np.array(err_yl)
    assert err_x.std() < tolerance     # x error std is less than 1e-6 pixel (in fine scale)
    assert err_y.std() < tolerance     # y error std is less than 1e-6 pixel (in fine scale)
    assert np.abs(err_x.mean()) < tolerance  # x bias is less than 1e-6 pixel (in fine scale)
    assert np.abs(err_y.mean()) < tolerance  # y bias is less than 1e-6 pixel (in fine scale)


@pytest.mark.parametrize("psf_file,tolerance,rebin,npoints", [
    (GAUSS_PSF, 1e-7, 1, 10),  # centroiding still works ok with oversampled gaussians
    (GAUSS_PSF, 1e-7, 2, 10),  # on a small window
    (GAUSS_PSF, 1e-7, 2, 100)
])
def test_many_sources(psf_file, tolerance, rebin, npoints):
    """Verify that an image with a many sources can have their positions
    recovered to a desired accuracy.

    This function works by generating one image with floating point positioned
    sources and performing a CoG over sub-regions of the image.
    """
    psf_cog = get_psf_cog(psf_file) - np.array([0.5, 0.5])

    # make image and check cog
    src = make_source(n_sources=npoints)
    err_xl = []
    err_yl = []
    max_rad = 5.0  # arcsec
    pixsize = 3.75e-3  # arcsec
    cog_width = 128 // rebin  # pixels
    pos = max_rad * get_gr_distributed_sources(npoints)
    src.gauss_pos[:, :] = pos.copy()
    width_as = 15
    image_gen = ImageGenerator(array_width_pix=5000, source=src, psfs_file=psf_file,
                               pixsize=pixsize, gauss_width_pix=32, which_psf=0, norm_psf=True)
    image_gen.main()
    im = image_gen.get_rebinned_cropped(rebin_factor=rebin, cropped_width_as=width_as)
    for new_pos in pos:
        cog_offset = np.round((new_pos + width_as / 2) / pixsize - cog_width / 2).astype(np.int32) // rebin
        assert np.all(cog_offset > 0) and np.all((cog_offset + cog_width) < im.shape[0])
        cog_x, cog_y = get_cog_windowed(im, cog_offset[0], cog_offset[1], cog_width)
        # measure error in pixels:
        err_xl.append(cog_x * rebin - new_pos[0] / pixsize - psf_cog[0])
        err_yl.append(cog_y * rebin - new_pos[1] / pixsize - psf_cog[1])
    err_x = np.array(err_xl)
    err_y = np.array(err_yl)
    assert err_x.std() < tolerance     # x error std is less than 1e-6 pixel (in fine scale)
    assert err_y.std() < tolerance     # y error std is less than 1e-6 pixel (in fine scale)
    assert np.abs(err_x.mean()) < tolerance  # x bias is less than 1e-6 pixel (in fine scale)
    assert np.abs(err_y.mean()) < tolerance  # y bias is less than 1e-6 pixel (in fine scale)


@pytest.mark.parametrize("psf_file,rebin,npoints", [
    (GAUSS_PSF, 1, 10),
    (GAUSS_PSF, 2, 10),
    (E2E_PSF, 1, 10),
    (E2E_PSF, 2, 10),
    (E2E_PSF, 2, 100)
])
def test_batching_stars(psf_file, rebin, npoints):
    """verify that placing one star in the field at a time is the same as doing a batch
    of many stars all at once
    """
    # make image and check cog
    src = make_source(n_sources=npoints)
    max_rad = 5.0  # arcsec
    pixsize = 3.75e-3  # arcsec
    pos = max_rad * get_gr_distributed_sources(npoints)
    src.gauss_pos[:, :] = pos.copy()
    width_as = 15
    image_gen = ImageGenerator(array_width_pix=5000, source=src, psfs_file=psf_file,
                               pixsize=pixsize, gauss_width_pix=32, which_psf=0, norm_psf=True)
    image_gen.main()
    im_batched = image_gen.get_rebinned_cropped(rebin_factor=rebin, cropped_width_as=width_as)

    # make image and check cog
    src = make_source()
    im_stacked = np.zeros([4000 // rebin, 4000 // rebin])
    for new_pos in pos:
        src.gauss_pos[:] = new_pos.copy()
        image_gen = ImageGenerator(array_width_pix=5000, source=src, psfs_file=psf_file,
                                   pixsize=pixsize, gauss_width_pix=32, which_psf=0, norm_psf=True)
        image_gen.main()
        im_stacked += image_gen.get_rebinned_cropped(rebin_factor=rebin, cropped_width_as=width_as)

    assert np.allclose(im_batched, im_stacked)


# At this point in the tests, we can be convinced that:
#  - photometry is conserved (assuming the sampled PSFs capture all of the
#    flux in their windows),
#  - astrometry is conserved (up to a constant shift in the field which is
#    dictated by the conventions used)
#  - stacking many frames of single stars is the same as generating one field
#    with all of those stars at once.

def test_field_varyiability():
    pass


def test_polychromatic_photometry():
    pass


def test_polychromatic_astrometry():
    pass


def test_noise_statistics():
    pass
