# About Stop move when probe tripped

Linuxcnc v2.8 stops move when probe tripped for safety in all modes. This is a good approach.
It is possible to exclude stops in AUTO mode, i.e. when the g-code program is being executed.

We can use 'demux' to convert the motion-mode into a bit output, though inconveniently motion-type is signed and demux wants unsigned, so we need to also use 'conv_s32_u32' and also an 'and2' 'or2' 'not' to disable the probe input in AUTO mode.
To do this, you need to add the .hal file of your machine with the functions and connections below.
Please match the quantities and numbers of each function to your configuration if they are already in use.

```sh
loadrt or2 count=1
loadrt demux personality=7
loadrt conv_s32_u32
loadrt and2 count=1
loadrt not count=1
...
```

```sh
addf demux.0  servo-thread
addf conv-s32-u32.0 servo-thread
addf and2.0 servo-thread
addf or2.0 servo-thread
addf not.0 servo-thread
...
```

```sh
net m-type motion.motion-type => conv-s32-u32.0.in
net m-type-u conv-s32-u32.0.out => demux.0.sel-u32
net mode-auto halui.mode.is-auto => not.0.in
net mode-auto-not not.0.out => or2.0.in0
net probing_in_auto demux.0.out-05 => or2.0.in1
net probing or2.0.out => and2.0.in0
net probe-pin  {your probe source} => and2.0.in1
net checked-probe and2.0.out => motion.probe-input
...
```
