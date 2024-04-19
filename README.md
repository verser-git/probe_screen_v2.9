# Probe Screen for LinuxCNC 2.8

## Info

Probe Screen v2.9 - all commonly used probe macros on one stylish screen, intuitive look, with minimal steps to set up.

Сhanges:
- Created for linuxcnc v2.9
- Support for Axis and Gmoccapy interfaces for screen sizes from 1280x1024
- Support metric and imperial systems


## Install

1. See "psng/install_del_from_your.hal"
   Delete (or comment) from all .hal files lines of the form:

   ```sh
   #loadusr -W hal_manualtoolchange
   #net tool-change iocontrol.0.tool-change => hal_manualtoolchange.change
   #net tool-changed iocontrol.0.tool-changed <= hal_manualtoolchange.changed
   #net tool-number iocontrol.0.tool-prep-number => hal_manualtoolchange.number
   ```

2. See "psng/install_add_to_your.ini" Add to your .ini settings, substitute your own constants.

3. The following folders from the archive are placed in configuration folder:

   ```sh
   /python
   /psng
   ```

4. Only for DISPLAY = axis: Copy .axisrc to your home ~/ folder. If you are already using .axisrc, then only add to your file contents of this .axisrc.

## Notes for DISPLAY = axis

By default, the Probe Screen doesn't fit in the 1280x1024 screen a bit, so some tweaks have been made to the .axisrc to expand the area. Details in axis_prepare folder.

## Notes for DISPLAY = gmoccapy

Gmoccapy intercepts MANUAL-MDI-AUTO mode switching events and closes the Probe Screen.
To avoid this, editing with root rights of the system file /usr/bin/gmoccapy is required
Details in gmoccapy_prepare folder.

## About Stop move when probe tripped

Linuxcnc v2.8 stops move when probe tripped for safety in all modes. This is a good approach.
It is possible to exclude stops in AUTO mode, i.e. when the g-code program is being executed.
This approach is described in no_stop_in_auto folder

## Use

Set the probe in the spindle.

Move manually probe for Z about 2-10 mm above the workpiece surface,
and for XY about the position indicated by the colored dot on the appropriate button Probe Screen.

Fill parameters. Meaning of the parameters should be clear from the names and pictures (the name pop up when approaching the mouse). If you change the parameters are automatically saved in .pref .

Hit **only** the button that corresponds to the position of the probe above the workpiece. For the other buttons - you **must** move the probe to another position above the workpiece.

You do not need to expose offsets for tool "Probe", the program desired zero offsets for the current tool makes herself, and G-code works off all in relative coordinates.
In fact, you can use the application immediately after the Home.

Any of the search ends at XY moving at the desired point (or edge, or corner, or center), Z remains in the original position.

More info <https://vers.ge/en/blog/useful-articles/probe-screen-v28>
Discussion on the forum linuxcnc.org: <https://forum.linuxcnc.org/49-basic-configuration/29187-work-with-probe>

## License

   This is a plugin for LinuxCNC v2.9
   Probe Screen is Copyright (c) 2024 Serguei Glavatski ( verser  from forum.linuxcnc.org and cnc-club.ru )
   <info@vers.ge>

   This program is free software; you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation; either version 2 of the License, or
   (at your option) any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with this program; if not, write to the Free Software
   Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
