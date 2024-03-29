import argparse, numpy as np, sounddevice, struct, sys, wave
from scipy import fft, signal

ap = argparse.ArgumentParser()
ap.add_argument(
    "-o", "--outfile",
    help="wav output file",
)
ap.add_argument(
    "-b", "--blocksize",
    help="block size in frames",
    type=int,
    default = 8,
)
ap.add_argument(
    "-a", "--algorithm",
    help="convolution algorithm",
    choices=["python", "convolve", "convolve-direct", "convolve-fft"],
    default="convolve",
)
ap.add_argument(
    "-p", "--play",
    help="play when generating output",
    action="store_true",
)
ap.add_argument(
    "wavfile",
    help="wav input file",
)
args = ap.parse_args()

if args.outfile is not None:
    play_anyway = args.play
else:
    play_anyway = True

blocksize = args.blocksize

# Read a wave file.
def read(filename):
    with wave.open(filename, "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        nframes = w.getnframes()
        frames = w.readframes(nframes)
        framedata = struct.unpack(f"<{nframes}h", frames)
        samples = [s / (1 << 15) for s in framedata]
        return w.getparams(), samples, w.getframerate()

# Collect the samples.
params, samples, sample_rate = read(args.wavfile)

# Write a wave file.
def write(f, samples, params):
    nframes = len(samples)
    params = list(params)
    params[3] = nframes
    params = tuple(params)
    framedata = [int(s * (1 << 15)) for s in samples]
    frames = struct.pack(f"<{nframes}h", *framedata)
    with wave.open(f, "wb") as w:
        w.setparams(params)
        w.writeframes(frames)

# Play a tone on the computer.
def play(samples):
    # Set up and start the stream.
    stream = sounddevice.RawOutputStream(
        samplerate = sample_rate,
        blocksize = blocksize,
        channels = 1,
        dtype = 'float32',
    )
    stream.start()

    # Write the samples.
    wav = iter(samples)
    done = False
    while not done:
        buffer = list()
        for _ in range(blocksize):
            try:
                sample = next(wav)
            except StopIteration:
                done = True
                break
            buffer.append(sample)
        pbuffer = struct.pack(f"{len(buffer)}f", *buffer)
        assert not stream.write(pbuffer), "overrun"

    # Tear down the stream.
    stream.stop()
    stream.close()

# Filter with blocksize 3
#     a b c d e 0 0
#     0 a b c d e 0
#   + 0 0 a b c d e
#   ---------------
#     a/3 (a+b)/3 (a+b+c)/3 ...
def filter_python(samples):
    outsamples = np.append(samples, np.array([0.0] * (blocksize - 1)))
    for i in range(1, blocksize):
        outsamples += np.concatenate((
            np.array([0.0] * i),
            samples,
            np.array([0.0] * (blocksize - i - 1)),
        ))
    outsamples /= blocksize
    return outsamples

def filter_convolve(samples, method="auto"):
    window = np.array([1.0 / blocksize] * blocksize)
    outsamples = signal.convolve(samples, window, method=method)
    return outsamples

if args.algorithm == "python":
    outsamples = filter_python(samples)
elif args.algorithm == "convolve-direct":
    outsamples = filter_convolve(samples, method="direct")
elif args.algorithm == "convolve-fft":
    outsamples = filter_convolve(samples, method="fft")
elif args.algorithm == "convolve":
    outsamples = filter_convolve(samples)
else:
    assert False

outsamples = np.clip(outsamples, -0.95, 0.95)

# Play the result.
if args.outfile:
    write(args.outfile, outsamples, params)
if play_anyway:
    play(outsamples)
