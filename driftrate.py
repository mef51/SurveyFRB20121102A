import matplotlib.pyplot as plt
import numpy as np
import scipy.optimize

def findCenter(burstwindow):
	freqspectrum = burstwindow.sum(axis=1)[:, None]
	freqi = np.indices(freqspectrum.shape)[0]
	return np.nansum(freqi*freqspectrum) / np.nansum(freqspectrum)

def structureParameter(wfall, dt, tstart, tend):
	"""
	wip. see eq. 1 in gajjar et al. 2018
	dt     - time resolution
	tstart - chan #
	tend   - chan #
	"""
	n = (tend - tstart)
	ts = np.nanmean(wfall, axis=0)
	struct = 0
	for i in enumerate(ts[tstart:tend]):
		struct += abs((ts[i] - ts[i+1]) / dt)

	return struct/n

def subband(wfall, nsub):
	nchan, nsamp = wfall.shape
	sub_factor = nchan // nsub
	return np.nanmean(wfall.reshape(-1, sub_factor, nsamp), axis=1)

def subsample(m, nfreq, ntime):
	""" m : 2x2 array """
	n = np.nanmean(m.reshape(-1, m.shape[0]//nfreq, m.shape[1]), axis=1)
	return np.nanmean(n.reshape(n.shape[0], -1, n.shape[1]//ntime), axis=2)

def subtractbg(wfall, tleft: int=0, tright: int=1):
	return wfall - wfall[:, tleft:tright].mean(axis=1)[:, None]

def moments(data):
	"""Returns (height, x, y, width_x, width_y)
	the gaussian parameters of a 2D distribution by calculating its
	moments """
	total = data.sum()
	X, Y = np.indices(data.shape)
	x = (X*data).sum()/total
	y = (Y*data).sum()/total
	col = data[:, int(y)]
	width_x = np.sqrt(abs((np.arange(col.size)-y)**2*col).sum()/col.sum())
	row = data[int(x), :]
	width_y = np.sqrt(abs((np.arange(row.size)-x)**2*row).sum()/row.sum())
	height = data.max()
	return height, x, y, width_x, width_y, 2.0

def twoD_Gaussian(point, amplitude, xo, yo, sigma_x, sigma_y, theta):
	y, x = point
	xo = float(xo)
	yo = float(yo)
	a = (np.cos(theta)**2)/(2*sigma_x**2) + (np.sin(theta)**2)/(2*sigma_y**2)
	b = (np.sin(2*theta))/(2*sigma_x**2) - (np.sin(2*theta))/(2*sigma_y**2)
	c = (np.sin(theta)**2)/(2*sigma_x**2) + (np.cos(theta)**2)/(2*sigma_y**2)
	g = amplitude*np.exp( - a*((x-xo)**2) - b*(x-xo)*(y-yo) - c*((y-yo)**2))
	return g.ravel()

def fitgaussiannlsq(data, p0=[], sigma=0, bounds=(-np.inf, np.inf)):
	# use curve-fit (non-linear leastsq)
	x = range(0, data.shape[1]); y = range(0, data.shape[0])
	x, y = np.meshgrid(x, y)
	p0 = moments(data) if p0 == [] else p0
	sigma = np.zeros(len(data.ravel())) + sigma
	popt, pcov = scipy.optimize.curve_fit(twoD_Gaussian, (y, x), data.ravel(), p0=p0, sigma=sigma,
										  absolute_sigma=True, bounds=bounds)
	return popt, pcov

def _dedisperse(wfall, dm, freq, dt):
	"""Dedisperse a dynamic spectrum.

	Parameters
	----------
	wfall : array_like
		Dynamic spectra of shape (nchan, nsamp).
	dm : float
		Dispersion measure to dedisperse to, in pc cm-3.
	freq : array_like
		Center frequencies of all channels, in MHz. Should have shape nchan.
	dt : float
		Sampling time, in s.

	Returns
	-------
	wfall : array_like
		Dedispersed dynamic spectra of shape (nchan, nsamp).

	"""
	k_dm = 1. / 2.41e-4
	dedisp = np.zeros_like(wfall)

	ref_freq = freq[0]### ORIGINAL
	# ref_freq = freq[-1]
	# print("ref_freq", ref_freq)

	shift = (k_dm * dm * (ref_freq ** -2 - freq ** -2) / dt) ### ORIGINAL (low freq anchor)
	# shift = (k_dm * dm * (freq ** -2 - ref_freq ** -2) / dt)
	shift = shift.round().astype(int)

	for i, ts in enumerate(wfall):
		dedisp[i] = np.roll(ts, shift[i])

	return dedisp

def dedisperse(intensity, DM, nu_low, df_mhz, dt_ms, cshift=0):
	dedispersed = np.copy(intensity)

	shifts = [0 for i in range(0, len(intensity))]
	high_ref_freq = nu_low + len(dedispersed)*df_mhz
	low_ref_freq  = nu_low
	#k_dm = 4.1488064239e6 # kulkarni
	k_dm = 4.14937759336e6 # pulsar community
	for i, row in enumerate(dedispersed): # i == 0 corresponds to bottom of the band
		nu_i = nu_low + i*df_mhz
		# High frequency anchor
		deltat = - k_dm * (nu_i**-2 - high_ref_freq**-2) * DM

		# Low frequency anchor
		#deltat = 4.14937759336e6 * (low_ref_freq**-2 - nu_i**-2) * DM

		channelshift = int(round(deltat/dt_ms))
		dedispersed[i] = np.roll(dedispersed[i], channelshift)

	# optionally center view
	dedispersed = np.roll(dedispersed, cshift, axis=1)

	return dedispersed

def getExtents(wfall, df:float=1.0, dt:float=1.0, lowest_freq:float=1.0):
	extents = (0,
			   dt*wfall.shape[1],
			   lowest_freq,
			   lowest_freq + df*wfall.shape[0])

	corrextents = (-extents[1], extents[1], -(extents[3]-extents[2])*2, (extents[3]-extents[2])*2)
	return extents, corrextents

def autocorr2d(data):

	# Returns a 2D autocorrelation computed via an intermediate FFT

	# Number of data pts
	nx, ny = data.shape[0], data.shape[1]

	padded = np.append(data, np.zeros((nx,ny)), axis=0)
	padded = np.append(padded, np.zeros((2*nx,ny)), axis=1)

	# Perform the FFT
	data_dft = np.fft.fft2(padded)

	# DFT of auto-correlation is simply (conjugate) multiplication
	# Elt-wise multiplication of fft
	data_ac_dft = np.multiply(np.conjugate(data_dft), data_dft)

	# Inverse FFT to return to time
	# Note this array will be half-shifted
	result_shifted = np.fft.ifft2(data_ac_dft)

	# Flip the result array around
	temp_array_a = np.empty(result_shifted.shape)
	temp_array_b = np.empty(result_shifted.shape)

	# Flip in x:
	temp_array_a[0:nx,:] = result_shifted[nx-1:2*nx-1,:]
	temp_array_a[nx:2*nx-1,:] = result_shifted[0:nx-1,:]
	# Flip in y:
	temp_array_b[:,0:ny] = temp_array_a[:,ny-1:2*ny-1]
	temp_array_b[:,ny:2*ny-1] = temp_array_a[:,0:ny-1]

	return temp_array_b[:-1,:-1]#/float(nx*ny)

def processBurst(burstwindow, fres_MHz, tres_ms, lowest_freq, burstkey=1, p0=[], popt_custom=[],
				 bounds=(-np.inf, np.inf), nclip=None, clip=None, plot=False,
				 sigmawindow=(0,50),
				 verbose=True):
	"""
	Given a waterfall of a burst, will use the 2d autocorrelation+gaussian fitting method to
	find the drift and make a plot of the burst and fit.
	returns drift, drift_error, popt, perr, theta,	red_chisq, center_f
	"""

	corr = autocorr2d(burstwindow)

	if nclip != None or clip != None:
		corr = np.clip(corr, nclip, clip)

	#### Autocorr noise
	autocorr_sigma = np.std( corr[:, sigmawindow[0]:sigmawindow[1]] )

	#### Fit Gaussian to autocorrelation.
	try:
		if popt_custom != []:
			popt, perr = popt_custom, [-1,-1,-1,-1,-1,-1]
		else:
			popt, pcov = fitgaussiannlsq(corr, p0=p0, sigma=autocorr_sigma, bounds=bounds)
			perr = np.sqrt(np.diag(pcov))

		if verbose: print('fit parameters:', popt)
	except (RuntimeError, ValueError):
		if verbose: print('no fit found')
		popt, perr = [-1,-1,-1,-1,-1,-1], [-1,-1,-1,-1,-1,-1]
		if popt_custom != []:
			popt = popt_custom

	x, y = np.meshgrid(range(0, corr.shape[1]), range(0, corr.shape[0]))
	fitmap = twoD_Gaussian((y, x), *popt).reshape(corr.shape[0], corr.shape[1])

	# calculate reduced chisquared
	residuals = corr - fitmap
	chisq = np.sum((residuals / autocorr_sigma) ** 2)
	red_chisq = chisq / (corr.shape[0]*corr.shape[1] - len(popt)) # this is chisq/(M-N)

	# Calculate drifit
	theta = popt[5] if abs(popt[3]) > abs(popt[4]) else popt[5] - np.pi/2
	slope = np.tan(theta)
	conversion = fres_MHz / (tres_ms)
	drift = conversion * slope # MHz/ms
	theta_err = perr[-1]
	drift_error = conversion * (theta_err * (1/np.cos(theta))**2)

	# find center frequency
	center_f = findCenter(burstwindow)*fres_MHz + lowest_freq

	#### Plot
	if plot:
		_plotresult(burstwindow, corr, fitmap, burstkey, center_f, popt, fres_MHz, tres_ms, lowest_freq)

	return (
		drift,
		drift_error,
		popt,
		perr,
		theta,
		red_chisq,
		center_f,
		fitmap
	)

def plotStampcard():
	""" TODO: generalize the code that plots marthi's bursts from ReadDataSandbox.ipynb """
	pass

def _plotresult(burstwindow, corr, fitmap, burstkey, center_f, popt, freq_res, time_res,
				lowest_freq, ploti=None):
	fontsize = 22
	cmap = plt.get_cmap('gray')
	cmap.set_bad(color = 'w', alpha = 1.)

	extents = (0,
			   time_res*burstwindow.shape[1],
			   lowest_freq - freq_res/2.,
			   lowest_freq + freq_res*burstwindow.shape[0])

	corrextents = (-extents[1], extents[1], -(extents[3]-extents[2])*2, (extents[3]-extents[2])*2)

	# extents, corrextents = None, None

	nrows = 7
	aspect = 'auto'
	if ploti == None:
		plt.figure(figsize=(15, 12))
		plt.subplot(121)
	else:
		plt.subplot(nrows, 2, next(ploti))
	plt.title("Burst #{}".format(burstkey), fontsize=fontsize)
	plt.imshow(burstwindow, interpolation='none', aspect=aspect, cmap=cmap, extent=extents, origin='lower')
	# plt.axhline(y=center_f, c='k', ls='--', lw=3)
	plt.xlabel("Time (ms)")
	plt.ylabel("Frequency (MHz)")

	if ploti == None:
		plt.subplot(122)
	else:
		plt.subplot(nrows, 2, next(ploti))
	plt.title("Correlation #{}".format(burstkey), fontsize=fontsize)
	plt.imshow(corr, interpolation='none', aspect=aspect, cmap='gray', extent=corrextents, origin='lower')
	plt.xlabel("Time Shift (ms)")
	plt.ylabel("Frequency Shift (MHz)")
	plt.clim(0, np.max(corr)/20)

	if popt[0] > 0:
		plt.contour(fitmap, [popt[0]/4, popt[0]*0.9], colors='b', alpha=0.75, extent=corrextents,
					origin='lower')

