#!/usr/bin/env python
#
# Probe Screen is Copyright (c) 2015 Serguei Glavatski ( verser  from forum.linuxcnc.org and cnc-club.ru )
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; If not, see <http://www.gnu.org/licenses/>.

import math
import os
import sys
import hal
import hal_glib
import time
from datetime import datetime
from functools import wraps
from subprocess import PIPE, Popen

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Pango

import linuxcnc

from ps_preferences import ProbeScreenPreferences
from util import restore_task_mode

CONFIGPATH1 = os.environ["CONFIG_DIR"]


class ProbeScreen(object):
    # --------------------------
    #
    #  INIT
    #
    # --------------------------
   
    def __init__(self, halcomp, builder, useropts):
        self.builder = builder
        self.halcomp = halcomp
#        self.builder.add_from_file("psng/probe_screen.glade")
 #       self.builder.connect_signals()
#        self.halcomp = hal.component("probe")
#        self.halcomp.ready()
#        self.builder.connect_signals(self)
        #---------------------------
        # Base vars
        #---------------------------
        
        # Load the machines INI file
        self.inifile = linuxcnc.ini(os.environ["INI_FILE_NAME"])
        if not self.inifile:
            self.error_dialog("Error, no INI File given")

        # Which display is in use? AXIS / gmoccapy / unknown
        self.display = self.get_display() or "unknown"

        # LinuxCNC Command / Stat / Error Interfaces
        self.command = linuxcnc.command()
        self.stat = linuxcnc.stat()
        self.stat.poll()

        
        # History Area
        textarea = builder.get_object("textview1")
        self.buffer = textarea.get_property("buffer")

        # Warning Dialog
        self.window = builder.get_object("window1")

        
        # VCP Reload Action
        self._vcp_action_reload = self.builder.get_object("vcp_action_reload")

        # Load Probe Screen Preferences
        self.prefs = ProbeScreenPreferences(self.get_preference_file_path())


        # Results for history()
        self._h_probe_xp = 0
        self._h_probe_yp = 0
        self._h_probe_xm = 0
        self._h_probe_ym = 0
        self._h_probe_lx = 0
        self._h_probe_ly = 0
        self._h_probe_z = 0
        self._h_probe_d = 0
        self._h_probe_xc = 0
        self._h_probe_yc = 0
        self._h_probe_a = 0

        #---------------------------
        # Settings vars
        #---------------------------
        self.spbtn1_search_vel = self.builder.get_object("spbtn1_search_vel")
        self.spbtn1_probe_vel = self.builder.get_object("spbtn1_probe_vel")
        self.spbtn1_z_clearance = self.builder.get_object("spbtn1_z_clearance")
        self.spbtn1_probe_max = self.builder.get_object("spbtn1_probe_max")
        self.spbtn1_probe_latch = self.builder.get_object("spbtn1_probe_latch")
        self.spbtn1_probe_diam = self.builder.get_object("spbtn1_probe_diam")
        self.spbtn1_xy_clearance = self.builder.get_object("spbtn1_xy_clearance")
        self.spbtn1_edge_length = self.builder.get_object("spbtn1_edge_length")
        
        self.halcomp.newpin("ps_searchvel", hal.HAL_FLOAT, hal.HAL_OUT)
        self.halcomp.newpin("ps_probevel", hal.HAL_FLOAT, hal.HAL_OUT)
        self.halcomp.newpin("ps_z_clearance", hal.HAL_FLOAT, hal.HAL_OUT)
        self.halcomp.newpin("ps_probe_max", hal.HAL_FLOAT, hal.HAL_OUT)
        self.halcomp.newpin("ps_probe_latch", hal.HAL_FLOAT, hal.HAL_OUT)
        self.halcomp.newpin("ps_probe_diam", hal.HAL_FLOAT, hal.HAL_OUT)
        self.halcomp.newpin("ps_xy_clearance", hal.HAL_FLOAT, hal.HAL_OUT)
        self.halcomp.newpin("ps_edge_length", hal.HAL_FLOAT, hal.HAL_OUT)
        # spbtn initialization --> self.on_ps_hal_stat_metric_mode_changed


        # Init Delay compensation parameters
        self.spbtn_signal_delay = self.builder.get_object("spbtn_signal_delay")
        self.label_val_overmove = self.builder.get_object("label_val_overmove")
        self.label_overmove = self.builder.get_object("label_overmove")
        self.chk_signal_delay = self.builder.get_object("chk_signal_delay")
        self.chk_signal_delay.set_active(self.prefs.getpref("chk_signal_delay", False, bool))
        self.halcomp.newpin("chk_signal_delay", hal.HAL_BIT, hal.HAL_OUT)
        if self.chk_signal_delay.get_active():
            self.halcomp["chk_signal_delay"] = True
            self.spbtn_signal_delay.set_sensitive( True ) 
            self.label_val_overmove.set_visible(True)
            self.label_overmove.set_visible(True)
        else:
            self.halcomp["chk_signal_delay"] = False
            self.spbtn_signal_delay.set_sensitive( False ) 
            self.label_val_overmove.set_visible(False)
            self.label_overmove.set_visible(False)

        self.spbtn_signal_delay.set_value(
            self.prefs.getpref("ps_signal_delay", 0, float)
        )
        if self.spbtn_signal_delay.get_value() == 0:
            self.label_val_overmove.set_visible(False)
            self.label_overmove.set_visible(False)
        
        self.halcomp.newpin("ps_signal_delay", hal.HAL_FLOAT, hal.HAL_OUT)
        self.halcomp["ps_signal_delay"] = self.spbtn_signal_delay.get_value()

        # Init Use refinement measurement
        self.chk_use_fine = self.builder.get_object("chk_use_fine")
        self.chk_use_fine.set_active(self.prefs.getpref("chk_use_fine", False, bool))
        self.halcomp.newpin("chk_use_fine", hal.HAL_BIT, hal.HAL_OUT)
        if self.chk_use_fine.get_active():
            self.halcomp["chk_use_fine"] = True
        else:
            self.halcomp["chk_use_fine"] = False
        
        # Init ERR pin processing
        self.chk_error_signal = self.builder.get_object("chk_error_signal")
        self.chk_error_signal.set_active(self.prefs.getpref("chk_error_signal", False, bool))
        self.halcomp.newpin("ps_error_signal", hal.HAL_BIT, hal.HAL_IN)
        self.halcomp.newpin("chk_error_signal", hal.HAL_BIT, hal.HAL_OUT)
        if self.chk_use_fine.get_active():
            self.halcomp["chk_error_signal"] = True
        else:
            self.halcomp["chk_error_signal"] = False


        #---------------------------
        # Inside Outside Measurement vars
        #---------------------------
        self.xpym = self.builder.get_object("xpym")
        self.ym = self.builder.get_object("ym")
        self.xmym = self.builder.get_object("xmym")
        self.xp = self.builder.get_object("xp")
        self.center = self.builder.get_object("center")
        self.xm = self.builder.get_object("xm")
        self.xpyp = self.builder.get_object("xpyp")
        self.yp = self.builder.get_object("yp")
        self.xmyp = self.builder.get_object("xmyp")
        self.hole = self.builder.get_object("hole")


        #---------------------------
        # Length vars
        #---------------------------
        self.lx_out = self.builder.get_object("lx_out")
        self.lx_in = self.builder.get_object("lx_in")
        self.ly_out = self.builder.get_object("ly_out")
        self.ly_in = self.builder.get_object("ly_in")


        #---------------------------
        # Rotation vars
        #---------------------------
        self.hal_led_auto_rott = self.builder.get_object("hal_led_auto_rott")
        self.chk_auto_rott = self.builder.get_object("chk_auto_rott")
        self.spbtn_offs_angle = self.builder.get_object("spbtn_offs_angle")
        self.lbl_current_angle = self.builder.get_object("lbl_current_angle")
        self.btn_rot_hole2 = self.builder.get_object("btn_rot_hole2")

        self.chk_auto_rott.set_active(self.prefs.getpref("chk_auto_rott", False, bool))
        self.spbtn_offs_angle.set_value(self.prefs.getpref("ps_offs_angle", 0.0, float))

        self.halcomp.newpin("ps_offs_angle", hal.HAL_FLOAT, hal.HAL_OUT)
        self.halcomp.newpin("chk_auto_rott", hal.HAL_BIT, hal.HAL_OUT)

        self.halcomp["chk_auto_rott"] = self.chk_auto_rott.get_active()
        self.hal_led_auto_rott.hal_pin.set(self.chk_auto_rott.get_active())
        
        self.halcomp["ps_offs_angle"] = self.spbtn_offs_angle.get_value()
        self.lbl_current_angle.set_text("%.3f" % self.stat.rotation_xy)

        #---------------------------
        # Zero (Touch Off) vars
        #---------------------------
        self.chk_set_zero = self.builder.get_object("chk_set_zero")
        self.hal_led_set_zero = self.builder.get_object("hal_led_set_zero")
        self.spbtn_offs_x = self.builder.get_object("spbtn_offs_x")
        self.spbtn_offs_y = self.builder.get_object("spbtn_offs_y")
        self.spbtn_offs_z = self.builder.get_object("spbtn_offs_z")

        self.halcomp.newpin("chk_set_zero", hal.HAL_BIT, hal.HAL_OUT)
        self.halcomp.newpin("ps_offs_x", hal.HAL_FLOAT, hal.HAL_OUT)
        self.halcomp.newpin("ps_offs_y", hal.HAL_FLOAT, hal.HAL_OUT)
        self.halcomp.newpin("ps_offs_z", hal.HAL_FLOAT, hal.HAL_OUT)

        self.chk_set_zero.set_active(self.prefs.getpref("chk_set_zero", False, bool))

        if self.chk_set_zero.get_active():
            self.halcomp["chk_set_zero"] = True
            self.hal_led_set_zero.hal_pin.set(1)
        # spbtn initialization --> self.on_ps_hal_stat_metric_mode_changed


        #---------------------------
        # Arm vars
        #---------------------------
        self.chk_arm_enable = self.builder.get_object("chk_arm_enable")
        self.hal_led_arm_enable = self.builder.get_object("hal_led_arm_enable")
        self.spbtn_arm_delta_x = self.builder.get_object("spbtn_arm_delta_x")
        self.spbtn_arm_delta_y = self.builder.get_object("spbtn_arm_delta_y")
        self.btn_arm_is_zero = self.builder.get_object("btn_arm_is_zero")
        self.btn_spindle_is_zero = self.builder.get_object("btn_spindle_is_zero")

        self.halcomp.newpin("chk_arm_enable", hal.HAL_BIT, hal.HAL_OUT)
        self.halcomp.newpin("ps_arm_delta_x", hal.HAL_FLOAT, hal.HAL_OUT)
        self.halcomp.newpin("ps_arm_delta_y", hal.HAL_FLOAT, hal.HAL_OUT)

        self.chk_arm_enable.set_active(self.prefs.getpref("chk_arm_enable", False, bool))

        self.halcomp["chk_arm_enable"] = self.chk_arm_enable.get_active()
        self.hal_led_arm_enable.hal_pin.set(self.chk_arm_enable.get_active())
        if self.chk_arm_enable.get_active():
            self.spbtn_arm_delta_x.set_sensitive( True )
            self.spbtn_arm_delta_y.set_sensitive( True )
            self.btn_arm_is_zero.set_sensitive( True )
            self.btn_spindle_is_zero.set_sensitive( True )
        else:
            self.spbtn_arm_delta_x.set_sensitive( False )
            self.spbtn_arm_delta_y.set_sensitive( False )
            self.btn_arm_is_zero.set_sensitive( False )
            self.btn_spindle_is_zero.set_sensitive( False ) 
        # spbtn initialization --> self.on_ps_hal_stat_metric_mode_changed

        #---------------------------
        # Combi_DRO vars
        #---------------------------
        self.combi_dro_X1 = self.builder.get_object("combi_dro_X1");
        self.combi_dro_X1.joint_no = 0;
        self.combi_dro_Y1 = self.builder.get_object("combi_dro_Y1");
        self.combi_dro_Y1.joint_no = 1;
        self.combi_dro_Z1 = self.builder.get_object("combi_dro_Z1");
        self.combi_dro_Z1.joint_no = 2;
        #---------------------------
        # Jog vars
        #---------------------------
        self.jog_Xplus_btn = self.builder.get_object("jog_Xplus_btn")
        self.jog_Xminus_btn = self.builder.get_object("jog_Xminus_btn")
        self.jog_Yplus_btn = self.builder.get_object("jog_Yplus_btn")
        self.jog_Yminus_btn = self.builder.get_object("jog_Yminus_btn")        
        
        self.steps = self.builder.get_object("steps")
        self.incr_rbt_list = []  # we use this list to add hal pin to the button later
        self.jog_increments = []  # This holds the increment values
        self.distance = 0  # This global will hold the jog distance
        self.halcomp.newpin("jog-increment", hal.HAL_FLOAT, hal.HAL_OUT)
        
        self.faktor = 1.0              # needed to calculate velocities

        self._init_jog_increments()


        #---------------------------
        # Remap M6 vars
        #---------------------------
        self.frm_probe_pos = self.builder.get_object("frm_probe_pos")
        self.spbtn_setter_height = self.builder.get_object("spbtn_setter_height")
        self.spbtn_block_height = self.builder.get_object("spbtn_block_height")
        self.btn_probe_tool_setter = self.builder.get_object("btn_probe_tool_setter")
        self.btn_probe_workpiece = self.builder.get_object("btn_probe_workpiece")
        self.btn_tool_dia = self.builder.get_object("btn_tool_dia")
        self.tooledit1 = self.builder.get_object("tooledit1")
        self.label_probe_workpiece = self.builder.get_object("label_probe_workpiece")
        self.label_probe_tool_setter = self.builder.get_object("label_probe_tool_setter")
        self.chk_enbl_remap_m6 = self.builder.get_object("chk_enbl_remap_m6")
        self.chk_enbl_remap_m6.set_active( self.prefs.getpref( "enbl_remap_m6", False, bool ) )
        self.hal_led_enbl_remap_m6 = self.builder.get_object("hal_led_enbl_remap_m6")
        self.halcomp.newpin( "enbl_remap_m6", hal.HAL_BIT, hal.HAL_OUT )
        if self.chk_enbl_remap_m6.get_active():
            self.btn_probe_tool_setter.set_sensitive( True )
            self.btn_probe_workpiece.set_sensitive( True )
            self.spbtn_setter_height.set_sensitive( True )
            self.spbtn_block_height.set_sensitive( True )
            self.label_probe_workpiece.set_sensitive( True )
            self.label_probe_tool_setter.set_sensitive( True )           
            self.halcomp["enbl_remap_m6"] = True
            self.hal_led_enbl_remap_m6.hal_pin.set(1)
        else:
            self.btn_probe_tool_setter.set_sensitive( False )
            self.btn_probe_workpiece.set_sensitive( False  )
            self.spbtn_setter_height.set_sensitive( False  )
            self.spbtn_block_height.set_sensitive( False  )
            self.label_probe_workpiece.set_sensitive( False  )
            self.label_probe_tool_setter.set_sensitive( False  )           
            self.halcomp["enbl_remap_m6"] = False 
            self.hal_led_enbl_remap_m6.hal_pin.set(0)
        

        # make the pins for tool measurement
        self.halcomp.newpin("setterheight", hal.HAL_FLOAT, hal.HAL_OUT)
        self.halcomp.newpin("blockheight", hal.HAL_FLOAT, hal.HAL_OUT)
        # for manual tool change dialog
        self.halcomp.newpin("toolchange-number", hal.HAL_S32, hal.HAL_IN)
        self.halcomp.newpin("toolchange-prep-number", hal.HAL_S32, hal.HAL_IN)
        self.halcomp.newpin("toolchange-changed", hal.HAL_BIT, hal.HAL_OUT)
        pin = self.halcomp.newpin("toolchange-change", hal.HAL_BIT, hal.HAL_IN)
        hal_glib.GPin(pin).connect("value_changed", self.on_tool_change)

        self._init_tool_sensor_data()
 
        # spbtn initialization --> self.on_ps_hal_stat_metric_mode_changed
        
        # --------------------------
        #  MM vs INCH
        # --------------------------
        self.halcomp.newpin("ps_metric_mode", hal.HAL_BIT, hal.HAL_OUT)        
        self.halcomp["ps_metric_mode"] = self.prefs.getpref("ps_metric_mode", self.stat.program_units-1, bool) 
        # Set units before any moves or probes
        if ((self.stat.program_units-1) == 1):
            self.setunits = "G21"
        else:
            self.setunits = "G20"
        self.on_ps_hal_stat_metric_mode_changed(self, self.stat.program_units-1)
        

    # --------------------------
    #
    #  MDI Command Methods
    #
    # --------------------------
    @restore_task_mode
    def gcode(self, s, distance=None, data=None):
        self.command.mode(linuxcnc.MODE_MDI)
        self.command.wait_complete()
        for l in s.split("\n"):
            # Search for G1 followed by a space, otherwise we'll catch G10 too.
            if "G1 " in l:
                l += " F#<_ini[TOOLSENSOR]RAPID_SPEED>"
            time_in = 5
            if distance is not None:
                # set a non-default wait limit for wait_complete()
                time_in = 1 + (distance / self.ps_rapid_speed ) * 60
#            print("time_in=", time_in)
            self.command.mdi(l)
            self.command.wait_complete(time_in)
            if self.error_poll() == -1:
                return -1
        return 0

    @restore_task_mode
    def ocode(self, s, data=None):
        self.command.mode(linuxcnc.MODE_MDI)
        self.command.wait_complete()

        self.command.mdi(s)
        self.stat.poll()
        while self.stat.interp_state != linuxcnc.INTERP_IDLE:
            if self.error_poll() == -1:
                return -1
            self.command.wait_complete()
            self.stat.poll()
        self.command.wait_complete()
        if self.error_poll() == -1:
            return -1
        return 0

    def error_poll(self):
        if "axis" in self.display:
            # AXIS polls for errors every 0.2 seconds, so we wait slightly longer to make sure it's happened.
#            time.sleep(0.25)
            error_pin = Popen(
                "halcmd getp probe.user.error ", shell=True, stdout=PIPE
            ).stdout.read()

        elif "gmoccapy" in self.display:
            # gmoccapy polls for errors every 0.25 seconds, OR whatever value is in the [DISPLAY]CYCLE_TIME ini
            # setting, so we wait slightly longer to make sure it's happened.
            ms = int(self.inifile.find("DISPLAY", "CYCLE_TIME") or 250) + 50
#            time.sleep(ms / 100)

            error_pin = Popen(
                "halcmd getp gmoccapy.error ", shell=True, stdout=PIPE
            ).stdout.read()

        else:
            print("Unable to poll %s GUI for errors" % self.display)
            return -1
#        print("error_pin = ", error_pin	)
        if "TRUE" in error_pin.decode("utf-8"):
            text = "See notification popup"
            self.add_history("Error: %s" % text)
            print("error", text)
            self.command.mode(linuxcnc.MODE_MANUAL)
            self.command.wait_complete()
            return -1

        return 0

    # --------------------------
    #
    #  Utility Methods
    #
    # --------------------------
    def get_display(self):
        # gmoccapy or axis ?
        temp = self.inifile.find("DISPLAY", "DISPLAY")
        if not temp:
            print(
                "****  PROBE SCREEN GET INI INFO **** \n Error recognition of display type : %s"
                % temp
            )
        return temp

    def vcp_reload(self):
        """ Realods the VCP - e.g. after changing changing changing origin/zero points """
        self._vcp_action_reload.emit("activate")

    def get_preference_file_path(self):
        # we use probe_screen.pref in the config dir
        temp = os.path.join(CONFIGPATH1, "probe_screen.pref")
        print("****  probe_screen GETINIINFO **** \n Preference file path: %s" % temp)
        return temp

    def on_ps_hal_stat_metric_mode_changed(self, widget, metric_units):
        #  metric_units:
        #  = False                         # imperial units are active
        #  = True                           # metric units are active
        # for first call
        if metric_units != self.halcomp["ps_metric_mode"]:
            # metric_units = metric
            if metric_units:
                self.faktor = 25.4
            # metric_units = imperial
            else:
                self.faktor = (1.0 / 25.4)

        else:
            # display units equal machine units would be factor = 1,
            self.faktor = 1.0

#        print("ps_hal_stat_metric_mode_changed", "  self.stat.linear_units = ", self.stat.linear_units)
#        print("metric_units = ",metric_units, "ps_metric_mode = ",self.halcomp["ps_metric_mode"], "faktor =",self.faktor )
        if metric_units:
            self.setunits = "G21"
            # Settings
            # default values for mm
            tup = (300.0, 10.0, 4.0, 0.6, 2.0, 2.5, 2.5, 6.0)
            self.spbtn1_search_vel.set_digits(1)
            self.spbtn1_probe_vel.set_digits(2)
            self.spbtn1_z_clearance.set_digits(3)
            self.spbtn1_probe_max.set_digits(3)
            self.spbtn1_probe_latch.set_digits(3)
            self.spbtn1_probe_diam.set_digits(3)
            self.spbtn1_xy_clearance.set_digits(3)
            self.spbtn1_edge_length.set_digits(3)
            # Zero
            self.spbtn_offs_x.set_digits(3)
            self.spbtn_offs_y.set_digits(3)
            self.spbtn_offs_z.set_digits(3)
            # Arm
            self.spbtn_arm_delta_x.set_digits(3)
            self.spbtn_arm_delta_y.set_digits(3)
            # Remap M6
            self.spbtn_setter_height.set_digits(3)
            self.spbtn_block_height.set_digits(3)
        else:
            self.setunits = "G20"
            # Settings
            # default values for inches
            tup = (120.0, 4.0, 1.58, 1.0, 0.787, 1.0, 1.0, 2.4)
            self.spbtn1_search_vel.set_digits(2)
            self.spbtn1_probe_vel.set_digits(3)
            self.spbtn1_z_clearance.set_digits(4)
            self.spbtn1_probe_max.set_digits(4)
            self.spbtn1_probe_latch.set_digits(4)
            self.spbtn1_probe_diam.set_digits(4)
            self.spbtn1_xy_clearance.set_digits(4)
            self.spbtn1_edge_length.set_digits(4)
            # Zero
            self.spbtn_offs_x.set_digits(4)
            self.spbtn_offs_y.set_digits(4)
            self.spbtn_offs_z.set_digits(4)
            # Arm
            self.spbtn_arm_delta_x.set_digits(4)
            self.spbtn_arm_delta_y.set_digits(4)
            # Remap M6
            self.spbtn_setter_height.set_digits(4)
            self.spbtn_block_height.set_digits(4)

        # Settings
        self.spbtn1_search_vel.set_value(self.prefs.getpref("ps_searchvel", tup[0], float) * self.faktor)
        self.spbtn1_probe_vel.set_value(self.prefs.getpref("ps_probevel", tup[1], float) * self.faktor)
        self.spbtn1_z_clearance.set_value(self.prefs.getpref("ps_z_clearance", tup[2], float) * self.faktor)
        self.spbtn1_probe_max.set_value(self.prefs.getpref("ps_probe_max", tup[3], float) * self.faktor)
        self.spbtn1_probe_latch.set_value(self.prefs.getpref("ps_probe_latch", tup[4], float) * self.faktor)
        self.spbtn1_probe_diam.set_value(self.prefs.getpref("ps_probe_diam", tup[5], float) * self.faktor)
        self.spbtn1_xy_clearance.set_value(self.prefs.getpref("ps_xy_clearance", tup[6], float) * self.faktor)
        self.spbtn1_edge_length.set_value(self.prefs.getpref("ps_edge_length", tup[7], float) * self.faktor)
        self.halcomp["ps_searchvel"] = self.spbtn1_search_vel.get_value()
        self.halcomp["ps_probevel"] = self.spbtn1_probe_vel.get_value()
        self.halcomp["ps_z_clearance"] = self.spbtn1_z_clearance.get_value()
        self.halcomp["ps_probe_max"] = self.spbtn1_probe_max.get_value()
        self.halcomp["ps_probe_latch"] = self.spbtn1_probe_latch.get_value()
        self.halcomp["ps_probe_diam"] = self.spbtn1_probe_diam.get_value()
        self.halcomp["ps_xy_clearance"] = self.spbtn1_xy_clearance.get_value()
        self.halcomp["ps_edge_length"] = self.spbtn1_edge_length.get_value()
        # Zero
        self.spbtn_offs_x.set_value(self.prefs.getpref("ps_offs_x", 0.0, float) * self.faktor)
        self.spbtn_offs_y.set_value(self.prefs.getpref("ps_offs_y", 0.0, float) * self.faktor)
        self.spbtn_offs_z.set_value(self.prefs.getpref("ps_offs_z", 0.0, float) * self.faktor)
        self.halcomp["ps_offs_x"] = self.spbtn_offs_x.get_value()
        self.halcomp["ps_offs_y"] = self.spbtn_offs_y.get_value()
        self.halcomp["ps_offs_z"] = self.spbtn_offs_z.get_value()
        # Arm
        self.spbtn_arm_delta_x.set_value(self.prefs.getpref("ps_arm_delta_x", 0.0, float) * self.faktor)
        self.spbtn_arm_delta_y.set_value(self.prefs.getpref("ps_arm_delta_y", 0.0, float) * self.faktor)
        self.halcomp["ps_arm_delta_x"] = self.spbtn_arm_delta_x.get_value()
        self.halcomp["ps_arm_delta_y"] = self.spbtn_arm_delta_y.get_value()
        # Remap M6
        self.spbtn_setter_height.set_value(self.prefs.getpref("setterheight", 0.0, float) * self.faktor)
        self.spbtn_block_height.set_value(self.prefs.getpref("blockheight", 0.0, float) * self.faktor)
        self.halcomp["setterheight"] = self.spbtn_setter_height.get_value()
        self.halcomp["blockheight"] = self.spbtn_block_height.get_value()

        # Save units
        self.halcomp["ps_metric_mode"] = metric_units 
        self.prefs.putpref("ps_metric_mode", metric_units, bool) 


    def on_ps_hal_stat_current_z_rotation(self, widget, angle):
        self.lbl_current_angle.set_text("%.3f" % angle)
        #self.stat.rotation_xy()
    

    # --------------------------
    #
    #  History and Logging Methods
    #
    # --------------------------
    def add_history(
        self,
        tool_tip_text,
        s="",
        xm=None,
        xc=None,
        xp=None,
        lx=None,
        ym=None,
        yc=None,
        yp=None,
        ly=None,
        z=None,
        d=None,
        a=None,
    ):
        c = "{0: <10}".format(tool_tip_text)
        if "Xm" in s:
            c += "X-=%.4f " % xm
            self._h_probe_xm = xm
        if "Xc" in s:
            c += "Xc=%.4f " % xc
            self._h_probe_xc = xc
        if "Xp" in s:
            c += "X+=%.4f " % xp
            self._h_probe_xp = xp
        if "Lx" in s:
            c += "Lx=%.4f " % lx
            self._h_probe_lx = lx
        if "Ym" in s:
            c += "Y-=%.4f " % ym
            self._h_probe_ym = ym
        if "Yc" in s:
            c += "Yc=%.4f " % yc
            self._h_probe_yc = yc
        if "Yp" in s:
            c += "Y+=%.4f " % yp
            self._h_probe_yp = yp
        if "Ly" in s:
            c += "Ly=%.4f " % ly
            self._h_probe_ly = ly
        if "Z" in s:
            c += "Z=%.4f " % z
            self._h_probe_z = z
        if "D" in s:
            c += "D=%.4f" % d
            self._h_probe_d = d
        if "A" in s:
            c += "Angle=%.3f" % a
            self._h_probe_a = a

        self.add_history_text(c)

    def add_history_text(self, text):
        # Prepend a timestamp to all History lines
        text = datetime.now().strftime("%H:%M:%S  ") + text

        # Remove the oldest history entries when we have a large
        # number of entries.
        i = self.buffer.get_end_iter()
        if i.get_line() > 1000:
            i.backward_line()
            self.buffer.delete(i, self.buffer.get_end_iter())

        # Add the line of text to the top of the history
        i.set_line(0)
        self.buffer.insert(i, "%s \n" % text)

    def _dialog(
        self, gtk_type, gtk_buttons, message, secondary=None, title=_("Probe Screen NG")
    ):
        """ displays a dialog """
        dialog = Gtk.MessageDialog(
            self.window,
            Gtk.DialogFlags.DESTROY_WITH_PARENT,
            gtk_type,
            gtk_buttons,
            message,
        )
        # if there is a secondary message then the first message text is bold
        if secondary:
            dialog.format_secondary_text(secondary)
        dialog.set_keep_above(True)
        dialog.show_all()
        dialog.set_title(title)
        responce = dialog.run()
        dialog.destroy()
        return responce == Gtk.ResponseType.YES

    # display warning dialog
    def warning_dialog(self, message, secondary = None, title = _("Probe Screen")):
        dialog = Gtk.MessageDialog(self.window,
                                   Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                   Gtk.MessageType.INFO, Gtk.ButtonsType.NONE, message)
        # if there is a secondary message then the first message text is bold
        if secondary:
            dialog.format_secondary_text(secondary)
        ok_button = Gtk.Button.new_with_mnemonic("_Ok")
        ok_button.set_size_request(-1, 56)
        ok_button.connect("clicked",lambda w:dialog.response(Gtk.ResponseType.OK))
        box = Gtk.HButtonBox()
        box.add(ok_button)
        dialog.action_area.add(box)
        dialog.set_border_width(5)
        dialog.show_all()
        dialog.set_title(title)
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.OK

    def error_dialog(self, message, secondary=None, title=_("Probe Screen NG")):
        """ displays a warning dialog and exits the probe screen"""
        self._dialog(Gtk.MessageType.ERROR, Gtk.ButtonsType.CANCEL, message, secondary, title)
        sys.exit(1)

    # --------------------------
    #
    #  Generic Probe Movement Methods
    #
    # --------------------------
    def z_clearance_down(self, data=None):
        # move Z - z_clearance
        s = """%s
        G91
        G1 Z-%f
        G90""" % (
            self.setunits, 
            self.halcomp["ps_z_clearance"]
        )
        if self.gcode(s) == -1:
            return -1
        return 0

    def z_clearance_up(self, data=None):
        # move Z + z_clearance
        s = """%s
        G91
        G1 Z%f
        G90""" % (
            self.setunits, 
            self.halcomp["ps_z_clearance"]
        )
        if self.gcode(s) == -1:
            return -1
        return 0

    # --------------------------
    #
    #  Generic Position Calculations
    #
    # --------------------------
    def set_zerro(self, s="XYZ", x=0.0, y=0.0, z=0.0, rot=False):
        if rot:
          chk_set_zero=True
        else:
          chk_set_zero=self.halcomp["chk_set_zero"]
        if chk_set_zero:
            #  Z current position
            self.stat.poll()
            tmpz = (
                self.stat.position[2]
                - self.stat.g5x_offset[2]
                - self.stat.g92_offset[2]
                - self.stat.tool_offset[2]
            )
            # X zero position vs zero-arm position
            tmpx = self.halcomp["ps_offs_x"]
            if self.halcomp["chk_arm_enable"]:
                tmpx -= self.halcomp["ps_arm_delta_x"]
            # Y zero position vs zero-arm position
            tmpy = self.halcomp["ps_offs_y"]
            if self.halcomp["chk_arm_enable"]:
                tmpy -= self.halcomp["ps_arm_delta_y"]
                
            c = "G10 L20 P0"
            s = s.upper()
            if "X" in s:
                x += tmpx
                c += " X%s" % x
            if "Y" in s:
                y += tmpy
                c += " Y%s" % y
            if "Z" in s:
                tmpz = tmpz - z + self.halcomp["ps_offs_z"]
                c += " Z%s" % tmpz
            self.gcode(c)
            self.vcp_reload()
            time.sleep(1)


    def probed_position_with_offsets(self, s="" ):
        self.stat.poll()
        probed_position = list(self.stat.probed_position)
        coord = list(self.stat.probed_position)
        g5x_offset = list(self.stat.g5x_offset)
        g92_offset = list(self.stat.g92_offset)
        tool_offset = list(self.stat.tool_offset)
        # self.stat.linear_units will return machine units: 1.0 for metric and 1/25,4 for imperial
        # self.halcomp["ps_metric_mode"] is display units
        factor=1
        if self.halcomp["ps_metric_mode"] != int(self.stat.linear_units):
            if self.halcomp["ps_metric_mode"]:
                factor = 25.4
            else:
                factor = (1.0 / 25.4)
        
        for i in range(0, len(probed_position) - 1):
            coord[i] = (
                probed_position[i] - g5x_offset[i] - g92_offset[i] - tool_offset[i]
            )*factor
        # Eliminating the extra travel caused by the signal delay
        if "xplus" in s:
            N_axis=0
            direction=1
        if "xminus" in s:
            N_axis=0
            direction=-1
        if "yplus" in s:
            N_axis=1
            direction=1
        if "yminus" in s:
            N_axis=1
            direction=-1
        if "zplus" in s:
            N_axis=2
            direction=1
        if "zminus" in s:
            N_axis=2
            direction=-1
        if  s == "":
            N_axis=0
            direction=0
        if self.chk_signal_delay.get_active():
            if self.chk_use_fine.get_active():
                extra_travel = self.spbtn1_probe_vel.get_value() * self.spbtn_signal_delay.get_value() * direction / 60000
            else:
                extra_travel = self.spbtn1_search_vel.get_value() * self.spbtn_signal_delay.get_value() * direction / 60000
            coord[N_axis] = coord[N_axis] - extra_travel
            # Set Last overmove Label 
            self.label_val_overmove.set_text( " = %.5f" % extra_travel )            
        
        angl = self.stat.rotation_xy
        res = self._rott00_point(coord[0], coord[1], -angl)
        coord[0] = res[0]
        coord[1] = res[1]
        return coord


    def _rott00_point(self, x1=0.0, y1=0.0, a1=0.0):
        """ rotate around 0,0 point coordinates """
        coord = [x1, y1]
        if a1 != 0:
            t = math.radians(a1)
            coord[0] = x1 * math.cos(t) - y1 * math.sin(t)
            coord[1] = x1 * math.sin(t) + y1 * math.cos(t)
        return coord

    def length_x(self, xm=None, xp=None):
        """ Calculates a length in the X direction """
        # Use previous value for xm if not supplied
        if xm is None:
            xm = self._h_probe_xm
            # Use None if no previous value exists
            if xm == "":
                xm = None
            else:
                xm = float(xm)

        # Use previous value for xp if not supplied
        if xp is None:
            xp = self._h_probe_xp
            # Use None if no previous value exists
            if xp == "":
                xp = None
            else:
                xp = float(xp)

        res = 0

        if xm is None or xp is None:
            return res

        if xm < xp:
            res = xp - xm
        else:
            res = xm - xp

        return res

    def length_y(self, ym=None, yp=None):
        """ Calculates a length in the Y direction """
        # Use previous value for ym if not supplied
        if ym is None:
            ym = self._h_probe_ym
            # Use None if no previous value exists
            if ym == "":
                ym = None
            else:
                ym = float(ym)

        # Use previous value for yp if not supplied
        if yp is None:
            yp = self._h_probe_yp
            # Use None if no previous value exists
            if yp == "":
                yp = None
            else:
                yp = float(yp)

        res = 0

        if ym is None or yp is None:
            return res

        if ym < yp:
            res = yp - ym
        else:
            res = ym - yp

        return res

    # --------------------------
    #
    #  Generic UI Methods
    #
    # --------------------------
    def on_common_spbtn_key_press_event(self, pin_name, gtkspinbutton, data=None):
        keyname = Gdk.keyval_name(data.keyval)
        
        if keyname == "Return":
            # Drop the Italics
            gtkspinbutton.modify_font(Pango.FontDescription("normal"))
        elif keyname == "Escape":
            # Restore the original value
            gtkspinbutton.set_value(self.halcomp[pin_name])

            # Drop the Italics
            gtkspinbutton.modify_font(Pango.FontDescription("normal"))
        else:
            # Set to Italics
            gtkspinbutton.modify_font(Pango.FontDescription("italic"))

    def on_common_spbtn_value_changed(
        self, pin_name, gtkspinbutton, data=None, _type=float
    ):
        # Drop the Italics
        gtkspinbutton.modify_font(Pango.FontDescription("normal"))

        # Update the pin
        self.halcomp[pin_name] = gtkspinbutton.get_value()

        # Update the preferences
        self.prefs.putpref(pin_name, gtkspinbutton.get_value(), _type)

    
    # --------------------------
    #
    #  Generic Method Wrappers
    #
    # --------------------------
#    @classmethod
    def ensure_errors_dismissed(f):
        """ Ensures all errors have been dismissed, otherwise, shows a warning dialog """

        @wraps(f)
        def wrapper(self, *args, **kwargs):
            if self.error_poll() == -1:
                message = _("Please dismiss & act upon all errors")
                secondary = _("You can retry once done")
                self.warning_dialog(message, secondary=secondary)
                return -1

            # Execute wrapped function
            return f(self, *args, **kwargs)

        return wrapper


    # ----------------
    # Settings Buttons
    # ----------------
    def on_spbtn1_search_vel_key_press_event (self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_searchvel", gtkspinbutton, data)

    def on_spbtn1_search_vel_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_searchvel", gtkspinbutton, data)

    def on_spbtn1_probe_vel_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_probevel", gtkspinbutton, data)

    def on_spbtn1_probe_vel_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_probevel", gtkspinbutton, data)

    def on_spbtn1_probe_max_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_probe_max", gtkspinbutton, data)

    def on_spbtn1_probe_max_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_probe_max", gtkspinbutton, data)

    def on_spbtn1_probe_latch_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_probe_latch", gtkspinbutton, data)

    def on_spbtn1_probe_latch_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_probe_latch", gtkspinbutton, data)

    def on_spbtn1_probe_diam_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_probe_diam", gtkspinbutton, data)

    def on_spbtn1_probe_diam_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_probe_diam", gtkspinbutton, data)

    def on_spbtn1_xy_clearance_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_xy_clearance", gtkspinbutton, data)

    def on_spbtn1_xy_clearance_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_xy_clearance", gtkspinbutton, data)

    def on_spbtn1_edge_length_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_edge_length", gtkspinbutton, data)

    def on_spbtn1_edge_length_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_edge_length", gtkspinbutton, data)

    def on_spbtn1_z_clearance_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_z_clearance", gtkspinbutton, data)

    def on_spbtn1_z_clearance_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_z_clearance", gtkspinbutton, data)

    # ----------------
    # Signal Delay Button
    # ----------------
    def on_chk_signal_delay_toggled(self, gtkcheckbutton, data=None):
        self.spbtn_signal_delay.set_sensitive( gtkcheckbutton.get_active() )
        if self.spbtn_signal_delay.get_value() == 0:
            self.label_val_overmove.set_visible(False)
            self.label_overmove.set_visible(False)
        else:
            self.label_val_overmove.set_visible(gtkcheckbutton.get_active())
            self.label_overmove.set_visible(gtkcheckbutton.get_active())        
        self.halcomp["chk_signal_delay"] = gtkcheckbutton.get_active()
        self.prefs.putpref("chk_signal_delay", gtkcheckbutton.get_active(), bool)

    def on_spbtn_signal_delay_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_signal_delay", gtkspinbutton, data)

    def on_spbtn_signal_delay_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_signal_delay", gtkspinbutton, data)
        if gtkspinbutton.get_value() == 0:
            self.label_val_overmove.set_visible(False)
            self.label_overmove.set_visible(False)
        else:
            self.label_val_overmove.set_visible(True)
            self.label_val_overmove.set_text(" = 0")
            self.label_overmove.set_visible(True)

        

    # ----------------
    # Use refinement measurement
    # ----------------
    def on_chk_use_fine_toggled(self, gtkcheckbutton, data=None):
        self.halcomp["chk_use_fine"] = gtkcheckbutton.get_active()
        self.prefs.putpref("chk_use_fine", gtkcheckbutton.get_active(), bool)
    
    # ----------------
    # ERR pin processing
    # ----------------
    def on_chk_error_signal_toggled(self, gtkcheckbutton, data=None):
        self.halcomp["chk_error_signal"] = gtkcheckbutton.get_active()
        self.prefs.putpref("chk_error_signal", gtkcheckbutton.get_active(), bool)


    # --------------  Command buttons -----------------
    #
    #               Measurement outside
    #
    # -------------------------------------------------
    
    # X+
    @ensure_errors_dismissed
    def on_xp_released(self, gtkbutton, data=None):
        # move X - xy_clearance
        s = """%s
        G91
        G1 X-%f
        G90""" % (
            self.setunits, self.halcomp["ps_xy_clearance"]
        )
        if self.gcode(s) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xplus.ngc
        if self.ocode("o<psng_xplus> call") == -1:
            return
        a = self.probed_position_with_offsets("xplus")
        xres = float(a[0] + 0.5 * self.halcomp["ps_probe_diam"])
        self.add_history(
            gtkbutton.get_tooltip_text(),
            "Xp",
            xp=xres,
            lx=self.length_x(xp=xres),
        )
        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # move to finded  point
        s = "G1 X%f" % (xres)
        if self.gcode(s) == -1:
            return
        self.set_zerro("X")

    # Y+
    @ensure_errors_dismissed
    def on_yp_released(self, gtkbutton, data=None):
        # move Y - xy_clearance
        s = """%s
        G91
        G1 Y-%f
        G90""" % (
            self.setunits, self.halcomp["ps_xy_clearance"]
        )
        if self.gcode(s) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_yplus.ngc
        if self.ocode("o<psng_yplus> call") == -1:
            return
        a = self.probed_position_with_offsets("yplus")
        yres = float(a[1]) + 0.5 * self.halcomp["ps_probe_diam"]
        self.add_history(
            gtkbutton.get_tooltip_text(),
            "Yp",
            yp=yres,
            ly=self.length_y(yp=yres),
        )
        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # move to finded  point
        s = "G1 Y%f" % (yres)
        if self.gcode(s) == -1:
            return
        self.set_zerro("Y")

    # X-
    @ensure_errors_dismissed
    def on_xm_released(self, gtkbutton, data=None):
        # move X + xy_clearance
        s = """%s
        G91
        G1 X%f
        G90""" % (
            self.setunits, self.halcomp["ps_xy_clearance"]
        )
        if self.gcode(s) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xminus.ngc
        if self.ocode("o<psng_xminus> call") == -1:
            return
        a = self.probed_position_with_offsets("xminus")
        xres = float(a[0] - 0.5 * self.halcomp["ps_probe_diam"])
        self.add_history(
            gtkbutton.get_tooltip_text(),
            "Xm",
            xm=xres,
            lx=self.length_x(xm=xres),
        )
        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # move to finded  point
        s = "G1 X%f" % (xres)
        if self.gcode(s) == -1:
            return
        self.set_zerro("X")

    # Y-
    @ensure_errors_dismissed
    def on_ym_released(self, gtkbutton, data=None):
        # move Y + xy_clearance
        s = """%s
        G91
        G1 Y%f
        G90""" % (
            self.setunits, self.halcomp["ps_xy_clearance"]
        )
        if self.gcode(s) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_yminus.ngc
        if self.ocode("o<psng_yminus> call") == -1:
            return
        a = self.probed_position_with_offsets("yminus")
        yres = float(a[1]) - 0.5 * self.halcomp["ps_probe_diam"]
        self.add_history(
            gtkbutton.get_tooltip_text(),
            "Ym",
            ym=yres,
            ly=self.length_y(ym=yres),
        )
        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # move to finded  point
        s = "G1 Y%f" % (yres)
        if self.gcode(s) == -1:
            return
        self.set_zerro("Y")

    # Corners
    # Move Probe manual under corner 2-3 mm
    # X+Y+
    @ensure_errors_dismissed
    def on_xpyp_released(self, gtkbutton, data=None):
        # move X - xy_clearance Y + edge_length
        s = """%s
        G91
        G1 X-%f Y%f
        G90""" % (
            self.setunits, 
            self.halcomp["ps_xy_clearance"],
            self.halcomp["ps_edge_length"],
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xplus.ngc
        if self.ocode("o<psng_xplus> call") == -1:
            return
        # show X result
        a = self.probed_position_with_offsets("xplus")
        xres = float(a[0] + 0.5 * self.halcomp["ps_probe_diam"])

        # move Z to start point up
        if self.z_clearance_up() == -1:
            return

        # move X + edge_length +xy_clearance,  Y - edge_length - xy_clearance
        tmpxy = self.halcomp["ps_edge_length"] + self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 X%f Y-%f
        G90""" % (
            self.setunits, 
            tmpxy,
            tmpxy,
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_yplus.ngc
        if self.ocode("o<psng_yplus> call") == -1:
            return
        # show Y result
        a = self.probed_position_with_offsets("yplus")
        yres = float(a[1]) + 0.5 * self.halcomp["ps_probe_diam"]

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XpYp",
            xp=xres,
            lx=self.length_x(xp=xres),
            yp=yres,
            ly=self.length_y(yp=yres),
        )
        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # move to finded  point
        s = "G1 X%f Y%f" % (xres, yres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.set_zerro("XY")

    # X+Y-
    @ensure_errors_dismissed
    def on_xpym_released(self, gtkbutton, data=None):
        # move X - xy_clearance Y + edge_length
        s = """%s
        G91
        G1 X-%f Y-%f
        G90""" % (
            self.setunits, 
            self.halcomp["ps_xy_clearance"],
            self.halcomp["ps_edge_length"],
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xplus.ngc
        if self.ocode("o<psng_xplus> call") == -1:
            return
        # show X result
        a = self.probed_position_with_offsets("xplus")
        xres = float(a[0] + 0.5 * self.halcomp["ps_probe_diam"])

        # move Z to start point up
        if self.z_clearance_up() == -1:
            return

        # move X + edge_length +xy_clearance,  Y + edge_length + xy_clearance
        tmpxy = self.halcomp["ps_edge_length"] + self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 X%f Y%f
        G90""" % (
            self.setunits, 
            tmpxy,
            tmpxy,
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_yminus.ngc
        if self.ocode("o<psng_yminus> call") == -1:
            return
        # show Y result
        a = self.probed_position_with_offsets("yminus")
        yres = float(a[1]) - 0.5 * self.halcomp["ps_probe_diam"]

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XpYm",
            xp=xres,
            lx=self.length_x(xp=xres),
            ym=yres,
            ly=self.length_y(ym=yres),
        )

        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # move to finded  point
        s = "G1 X%f Y%f" % (xres, yres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.set_zerro("XY")

    # X-Y+
    @ensure_errors_dismissed
    def on_xmyp_released(self, gtkbutton, data=None):
        # move X + xy_clearance Y + edge_length
        s = """%s
        G91
        G1 X%f Y%f
        G90""" % (
            self.setunits, 
            self.halcomp["ps_xy_clearance"],
            self.halcomp["ps_edge_length"],
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xminus.ngc
        if self.ocode("o<psng_xminus> call") == -1:
            return
        # show X result
        a = self.probed_position_with_offsets("xminus")
        xres = float(a[0] - 0.5 * self.halcomp["ps_probe_diam"])

        # move Z to start point up
        if self.z_clearance_up() == -1:
            return

        # move X - edge_length - xy_clearance,  Y - edge_length - xy_clearance
        tmpxy = self.halcomp["ps_edge_length"] + self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 X-%f Y-%f
        G90""" % (
            self.setunits, 
            tmpxy,
            tmpxy,
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_yplus.ngc
        if self.ocode("o<psng_yplus> call") == -1:
            return
        # show Y result
        a = self.probed_position_with_offsets("yplus")
        yres = float(a[1]) + 0.5 * self.halcomp["ps_probe_diam"]
        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XmYp",
            xm=xres,
            lx=self.length_x(xm=xres),
            yp=yres,
            ly=self.length_y(yp=yres),
        )
        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # move to finded  point
        s = "G1 X%f Y%f" % (xres, yres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.set_zerro("XY")

    # X-Y-
    @ensure_errors_dismissed
    def on_xmym_released(self, gtkbutton, data=None):
        # move X + xy_clearance Y - edge_length
        s = """%s
        G91
        G1 X%f Y-%f
        G90""" % (
            self.setunits, 
            self.halcomp["ps_xy_clearance"],
            self.halcomp["ps_edge_length"],
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xminus.ngc
        if self.ocode("o<psng_xminus> call") == -1:
            return

        # Calculate X result
        a = self.probed_position_with_offsets("xminus")
        xres = float(a[0] - 0.5 * self.halcomp["ps_probe_diam"])

        # move Z to start point up
        if self.z_clearance_up() == -1:
            return

        # move X - edge_length - xy_clearance,  Y + edge_length + xy_clearance
        tmpxy = self.halcomp["ps_edge_length"] + self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 X-%f Y%f
        G90""" % (
            self.setunits, 
            tmpxy,
            tmpxy,
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_yminus.ngc
        if self.ocode("o<psng_yminus> call") == -1:
            return
        # Calculate Y result
        a = self.probed_position_with_offsets("yminus")
        yres = float(a[1]) - 0.5 * self.halcomp["ps_probe_diam"]
        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XmYm",
            xm=xres,
            lx=self.length_x(xm=xres),
            ym=yres,
            ly=self.length_y(ym=yres),
        )
        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # move to finded  point
        s = "G1 X%f Y%f" % (xres, yres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.set_zerro("XY")

    # Center X+ X- Y+ Y-
    @ensure_errors_dismissed
    def on_xy_center_released(self, gtkbutton, data=None):
        # move X - edge_length- xy_clearance
        tmpx = self.halcomp["ps_edge_length"] + self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 X-%f
        G90""" % (
            self.setunits, 
            tmpx
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xplus.ngc
        if self.ocode("o<psng_xplus> call") == -1:
            return
        # Calculate X result
        a = self.probed_position_with_offsets("xplus")
        xpres = float(a[0]) + 0.5 * self.halcomp["ps_probe_diam"]

        # move Z to start point up
        if self.z_clearance_up() == -1:
            return

        # move X + 2 edge_length + 2 xy_clearance
        tmpx = 2 * (self.halcomp["ps_edge_length"] + self.halcomp["ps_xy_clearance"])
        s = """%s
        G91
        G1 X%f
        G90""" % (
            self.setunits, 
            tmpx
        )
        if self.gcode(s, 2*self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xminus.ngc

        if self.ocode("o<psng_xminus> call") == -1:
            return
        # Calculate X result
        a = self.probed_position_with_offsets("xminus")
        xmres = float(a[0]) - 0.5 * self.halcomp["ps_probe_diam"]
        xcres = 0.5 * (xpres + xmres)

        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # distance to the new center of X from current position
        #        self.stat.poll()
        #        to_new_xc=self.stat.position[0]-self.stat.g5x_offset[0] - self.stat.g92_offset[0] - self.stat.tool_offset[0] - xcres
        s = "G1 X%f" % (xcres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return

        # move Y - edge_length- xy_clearance
        tmpy = self.halcomp["ps_edge_length"] + self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 Y-%f
        G90""" % (
            self.setunits, 
            tmpy
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_yplus.ngc
        if self.ocode("o<psng_yplus> call") == -1:
            return

        # Calculate Y result
        a = self.probed_position_with_offsets("yplus")
        ypres = float(a[1]) + 0.5 * self.halcomp["ps_probe_diam"]

        # move Z to start point up
        if self.z_clearance_up() == -1:
            return

        # move Y + 2 edge_length + 2 xy_clearance
        tmpy = 2 * (self.halcomp["ps_edge_length"] + self.halcomp["ps_xy_clearance"])
        s = """%s
        G91
        G1 Y%f
        G90""" % (
            self.setunits, 
            tmpy
        )
        if self.gcode(s, 2*self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return

        # Start psng_yminus.ngc
        if self.ocode("o<psng_yminus> call") == -1:
            return

        # Calculate Y result
        a = self.probed_position_with_offsets("yminus")
        ymres = float(a[1]) - 0.5 * self.halcomp["ps_probe_diam"]

        # find, show and move to finded  point
        ycres = 0.5 * (ypres + ymres)
        diam = ymres - ypres

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XmXcXpLxYmYcYpLyD",
            xm=xmres,
            xc=xcres,
            xp=xpres,
            lx=self.length_x(xm=xmres, xp=xpres),
            ym=ymres,
            yc=ycres,
            yp=ypres,
            ly=self.length_y(ym=ymres, yp=ypres),
            d=diam,
        )
        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # move to finded  point
        s = "G1 Y%f" % (ycres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.set_zerro("XY")

    # --------------  Command buttons -----------------
    #
    #               Measurement inside
    #
    # -------------------------------------------------

    # Corners
    # Move Probe manual under corner 2-3 mm
    # X+Y+
    @ensure_errors_dismissed
    def on_xpyp1_released(self, gtkbutton, data=None):
        # move Y - edge_length X - xy_clearance
        s = """%s
        G91
        G1 X-%f Y-%f
        G90""" % (
            self.setunits, 
            self.halcomp["ps_xy_clearance"],
            self.halcomp["ps_edge_length"],
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xplus.ngc
        if self.ocode("o<psng_xplus> call") == -1:
            return
        # Calculate X result
        a = self.probed_position_with_offsets("xplus")
        xres = float(a[0]) + 0.5 * self.halcomp["ps_probe_diam"]

        # move X - edge_length Y - xy_clearance
        tmpxy = self.halcomp["ps_edge_length"] - self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 X-%f Y%f
        G90""" % (
            self.setunits, 
            tmpxy,
            tmpxy,
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        # Start psng_yplus.ngc
        if self.ocode("o<psng_yplus> call") == -1:
            return
        # Calculate Y result
        a = self.probed_position_with_offsets("yplus")
        yres = float(a[1]) + 0.5 * self.halcomp["ps_probe_diam"]

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XpYp",
            xp=xres,
            lx=self.length_x(xp=xres),
            yp=yres,
            ly=self.length_y(yp=yres),
        )

        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        # move to finded  point
        s = "G1 X%f Y%f" % (xres, yres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.set_zerro("XY")

    # X+Y-
    @ensure_errors_dismissed
    def on_xpym1_released(self, gtkbutton, data=None):
        # move Y + edge_length X - xy_clearance
        s = """%s
        G91
        G1 X-%f Y%f
        G90""" % (
            self.setunits, 
            self.halcomp["ps_xy_clearance"],
            self.halcomp["ps_edge_length"],
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xplus.ngc
        if self.ocode("o<psng_xplus> call") == -1:
            return
        # Calculate X result
        a = self.probed_position_with_offsets("xplus")
        xres = float(a[0]) + 0.5 * self.halcomp["ps_probe_diam"]

        # move X - edge_length Y + xy_clearance
        tmpxy = self.halcomp["ps_edge_length"] - self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 X-%f Y-%f
        G90""" % (
            self.setunits, 
            tmpxy,
            tmpxy,
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return

        # Start psng_yminus.ngc
        if self.ocode("o<psng_yminus> call") == -1:
            return

        # Calculate Y result
        a = self.probed_position_with_offsets("yminus")
        yres = float(a[1]) - 0.5 * self.halcomp["ps_probe_diam"]

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XpYm",
            xp=xres,
            lx=self.length_x(xp=xres),
            ym=yres,
            ly=self.length_y(ym=yres),
        )

        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        # move to finded  point
        s = "G1 X%f Y%f" % (xres, yres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.set_zerro("XY")

    # X-Y+
    @ensure_errors_dismissed
    def on_xmyp1_released(self, gtkbutton, data=None):
        # move Y - edge_length X + xy_clearance
        s = """%s
        G91
        G1 X%f Y-%f
        G90""" % (
            self.setunits, 
            self.halcomp["ps_xy_clearance"],
            self.halcomp["ps_edge_length"],
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xminus.ngc
        if self.ocode("o<psng_xminus> call") == -1:
            return

        # Calculate X result
        a = self.probed_position_with_offsets("xminus")
        xres = float(a[0]) - 0.5 * self.halcomp["ps_probe_diam"]

        # move X + edge_length Y - xy_clearance
        tmpxy = self.halcomp["ps_edge_length"] - self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 X%f Y%f
        G90""" % (
            self.setunits, 
            tmpxy,
            tmpxy,
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return

        # Start psng_yplus.ngc
        if self.ocode("o<psng_yplus> call") == -1:
            return

        # Calculate Y result
        a = self.probed_position_with_offsets("yplus")
        yres = float(a[1]) + 0.5 * self.halcomp["ps_probe_diam"]

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XmYp",
            xm=xres,
            lx=self.length_x(xm=xres),
            yp=yres,
            ly=self.length_y(yp=yres),
        )

        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        # move to finded  point
        s = "G1 X%f Y%f" % (xres, yres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.set_zerro("XY")

    # X-Y-
    @ensure_errors_dismissed
    def on_xmym1_released(self, gtkbutton, data=None):
        # move Y + edge_length X + xy_clearance
        s = """%s
        G91
        G1 X%f Y%f
        G90""" % (
            self.setunits, 
            self.halcomp["ps_xy_clearance"],
            self.halcomp["ps_edge_length"],
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xminus.ngc
        if self.ocode("o<psng_xminus> call") == -1:
            return
        # Calculate X result
        a = self.probed_position_with_offsets("xminus")
        xres = float(a[0]) - 0.5 * self.halcomp["ps_probe_diam"]

        # move X + edge_length Y - xy_clearance
        tmpxy = self.halcomp["ps_edge_length"] - self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 X%f Y-%f
        G90""" % (
            self.setunits, 
            tmpxy,
            tmpxy,
        )

        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return

        # Start psng_yminus.ngc
        if self.ocode("o<psng_yminus> call") == -1:
            return

        # Calculate Y result
        a = self.probed_position_with_offsets("yminus")
        yres = float(a[1]) - 0.5 * self.halcomp["ps_probe_diam"]

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XmYm",
            xm=xres,
            lx=self.length_x(xm=xres),
            ym=yres,
            ly=self.length_y(ym=yres),
        )

        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        # move to finded  point
        s = "G1 X%f Y%f" % (xres, yres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.set_zerro("XY")

    # Hole Xin- Xin+ Yin- Yin+
    @ensure_errors_dismissed
    def on_xy_hole_released(self, gtkbutton, data=None):
        if self.z_clearance_down() == -1:
            return
        # move X - edge_length Y + xy_clearance
        tmpx = self.halcomp["ps_edge_length"] - self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 X-%f
        G90""" % (
            self.setunits, 
            tmpx
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        # Start psng_xminus.ngc
        if self.ocode("o<psng_xminus> call") == -1:
            return
        # show X result
        a = self.probed_position_with_offsets("xminus")
        xmres = float(a[0]) - 0.5 * self.halcomp["ps_probe_diam"]

        # move X +2 edge_length - 2 xy_clearance
        tmpx = 2 * (self.halcomp["ps_edge_length"] - self.halcomp["ps_xy_clearance"])
        s = """%s
        G91
        G1 X%f
        G90""" % (
            self.setunits, 
            tmpx
        )
        if self.gcode(s, 2*self.halcomp["ps_edge_length"]) == -1:
            return
        # Start psng_xplus.ngc
        if self.ocode("o<psng_xplus> call") == -1:
            return
        # Calculate X result
        a = self.probed_position_with_offsets("xplus")
        xpres = float(a[0]) + 0.5 * self.halcomp["ps_probe_diam"]
        xcres = 0.5 * (xmres + xpres)

        # move X to new center
        s = """G1 X%f""" % (xcres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return

        # move Y - edge_length + xy_clearance
        tmpy = self.halcomp["ps_edge_length"] - self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 Y-%f
        G90""" % (
            self.setunits, 
            tmpy
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        # Start psng_yminus.ngc
        if self.ocode("o<psng_yminus> call") == -1:
            return
        # Calculate Y result
        a = self.probed_position_with_offsets("yminus")
        ymres = float(a[1]) - 0.5 * self.halcomp["ps_probe_diam"]

        # move Y +2 edge_length - 2 xy_clearance
        tmpy = 2 * (self.halcomp["ps_edge_length"] - self.halcomp["ps_xy_clearance"])
        s = """%s
        G91
        G1 Y%f
        G90""" % (
            self.setunits, 
            tmpy
        )
        if self.gcode(s, 2*self.halcomp["ps_edge_length"]) == -1:
            return
        # Start psng_yplus.ngc
        if self.ocode("o<psng_yplus> call") == -1:
            return

        # Calculate Y result
        a = self.probed_position_with_offsets("yplus")
        ypres = float(a[1]) + 0.5 * self.halcomp["ps_probe_diam"]

        # find, show and move to finded  point
        ycres = 0.5 * (ymres + ypres)
        diam = 0.5 * ((xpres - xmres) + (ypres - ymres))

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XmXcXpLxYmYcYpLyD",
            xm=xmres,
            xc=xcres,
            xp=xpres,
            lx=self.length_x(xm=xmres, xp=xpres),
            ym=ymres,
            yc=ycres,
            yp=ypres,
            ly=self.length_y(ym=ymres, yp=ypres),
            d=diam,
        )

        # move to center
        s = "G1 Y%f" % (ycres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        if gtkbutton.get_name() != "btn_rot_hole2":
            self.set_zerro("XY")


    # --------------
    # Length Buttons
    # --------------

    # Lx OUT
    @ensure_errors_dismissed
    def on_lx_out_released(self, gtkbutton, data=None):
        # move X - edge_length- xy_clearance
        tmpx = self.halcomp["ps_edge_length"] + self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 X-%f
        G90""" % (
            self.setunits, tmpx
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xplus.ngc
        if self.ocode("o<psng_xplus> call") == -1:
            return
        # show X result
        a = self.probed_position_with_offsets("xplus")
        xpres = float(a[0]) + 0.5 * self.halcomp["ps_probe_diam"]

        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # move to finded  point X
        s = "G1 X%f" % xpres
        if self.gcode(s) == -1:
            return

        # move X + 2 edge_length +  xy_clearance
        tmpx = 2 * self.halcomp["ps_edge_length"] + self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 X%f
        G90""" % (
            self.setunits, tmpx
        )
        if self.gcode(s, 2*self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xminus.ngc
        if self.ocode("o<psng_xminus> call") == -1:
            return
        # Calculate X result
        a = self.probed_position_with_offsets("xminus")
        xmres = float(a[0]) - 0.5 * self.halcomp["ps_probe_diam"]
        xcres = 0.5 * (xpres + xmres)

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XmXcXpLx",
            xm=xmres,
            xc=xcres,
            xp=xpres,
            lx=self.length_x(xm=xmres, xp=xpres),
        )
        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # go to the new center of X
        s = "G1 X%f" % (xcres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.set_zerro("X")

    # Ly OUT
    @ensure_errors_dismissed
    def on_ly_out_released(self, gtkbutton, data=None):
        # move Y - edge_length- xy_clearance
        tmpy = self.halcomp["ps_edge_length"] + self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 Y-%f
        G90""" % (
            self.setunits, tmpy
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_yplus.ngc
        if self.ocode("o<psng_yplus> call") == -1:
            return
        # Calculate Y result
        a = self.probed_position_with_offsets("yplus")
        ypres = float(a[1]) + 0.5 * self.halcomp["ps_probe_diam"]

        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # move to finded  point Y
        s = "G1 Y%f" % ypres
        if self.gcode(s) == -1:
            return

        # move Y + 2 edge_length +  xy_clearance
        tmpy = 2 * self.halcomp["ps_edge_length"] + self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 Y%f
        G90""" % (
            self.setunits, tmpy
        )
        if self.gcode(s, 2*self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_yminus.ngc
        if self.ocode("o<psng_yminus> call") == -1:
            return
        # show Y result
        a = self.probed_position_with_offsets("yminus")
        ymres = float(a[1]) - 0.5 * self.halcomp["ps_probe_diam"]

        # find, show and move to finded  point
        ycres = 0.5 * (ypres + ymres)

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "YmYcYpLy",
            ym=ymres,
            yc=ycres,
            yp=ypres,
            ly=self.length_y(ym=ymres, yp=ypres),
        )
        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # move to finded  point
        s = "G1 Y%f" % (ycres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.set_zerro("Y")

    # Lx IN
    @ensure_errors_dismissed
    def on_lx_in_released(self, gtkbutton, data=None):
        if self.z_clearance_down() == -1:
            return
        # move X - edge_length Y + xy_clearance
        tmpx = self.halcomp["ps_edge_length"] - self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 X-%f
        G90""" % (
            self.setunits, tmpx
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        # Start psng_xminus.ngc
        if self.ocode("o<psng_xminus> call") == -1:
            return
        # Calculate X result
        a = self.probed_position_with_offsets("xminus")
        xmres = float(a[0]) - 0.5 * self.halcomp["ps_probe_diam"]

        # move X +2 edge_length - 2 xy_clearance
        tmpx = 2 * (self.halcomp["ps_edge_length"] - self.halcomp["ps_xy_clearance"])
        s = """%s
        G91
        G1 X%f
        G90""" % (
            self.setunits, tmpx
        )
        if self.gcode(s, 2*self.halcomp["ps_edge_length"]) == -1:
            return
        # Start psng_xplus.ngc
        if self.ocode("o<psng_xplus> call") == -1:
            return
        # Calculate X result
        a = self.probed_position_with_offsets("xplus")
        xpres = float(a[0]) + 0.5 * self.halcomp["ps_probe_diam"]
        xcres = 0.5 * (xmres + xpres)

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XmXcXpLx",
            xm=xmres,
            xc=xcres,
            xp=xpres,
            lx=self.length_x(xm=xmres, xp=xpres),
        )
        # move X to new center
        s = """G1 X%f""" % (xcres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        self.set_zerro("X")

    # Ly IN
    @ensure_errors_dismissed
    def on_ly_in_released(self, gtkbutton, data=None):
        if self.z_clearance_down() == -1:
            return
        # move Y - edge_length + xy_clearance
        tmpy = self.halcomp["ps_edge_length"] - self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 Y-%f
        G90""" % (
            self.setunits, tmpy
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        # Start psng_yminus.ngc
        if self.ocode("o<psng_yminus> call") == -1:
            return

        # Calculate Y result
        a = self.probed_position_with_offsets("yminus")
        ymres = float(a[1]) - 0.5 * self.halcomp["ps_probe_diam"]

        # move Y +2 edge_length - 2 xy_clearance
        tmpy = 2 * (self.halcomp["ps_edge_length"] - self.halcomp["ps_xy_clearance"])
        s = """%s
        G91
        G1 Y%f
        G90""" % (
            self.setunits, tmpy
        )
        if self.gcode(s, 2*self.halcomp["ps_edge_length"]) == -1:
            return
        # Start psng_yplus.ngc
        if self.ocode("o<psng_yplus> call") == -1:
            return
        # Calculate Y result
        a = self.probed_position_with_offsets("yplus")
        ypres = float(a[1]) + 0.5 * self.halcomp["ps_probe_diam"]

        # find, show and move to finded  point
        ycres = 0.5 * (ymres + ypres)

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "YmYcYpLy",
            ym=ymres,
            yc=ycres,
            yp=ypres,
            ly=self.length_y(ym=ymres, yp=ypres),
        )

        # move to center
        s = "G1 Y%f" % (ycres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        self.set_zerro("Y")



    # --------------
    # Rotate Buttons
    # --------------
    def on_chk_auto_rott_toggled(self, gtkcheckbutton, data=None):
        self.halcomp["chk_auto_rott"] = gtkcheckbutton.get_active()
        self.hal_led_auto_rott.hal_pin.set(gtkcheckbutton.get_active())
        self.prefs.putpref("chk_auto_rott", gtkcheckbutton.get_active(), bool)

    def on_btn_set_angle_released(self, gtkbutton, data=None):
        self.prefs.putpref("ps_offs_angle", self.spbtn_offs_angle.get_value(), float)
        self._h_probe_a = self.spbtn_offs_angle.get_value()

        s = "G10 L2 P0"
        if self.chk_auto_rott.get_active():
            s += " X%.4f" % self.halcomp["ps_offs_x"]
            s += " Y%.4f" % self.halcomp["ps_offs_y"]
        else:
            self.stat.poll()
            x = self.stat.position[0]
            y = self.stat.position[1]
            s += " X%.4f" % x
            s += " Y%.4f" % y
        s += " R%.4f" % self.spbtn_offs_angle.get_value()
        print("s=", s)
        self.gcode(s)
        self.vcp_reload()
        time.sleep(1)

    def on_spbtn_offs_angle_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_offs_angle", gtkspinbutton, data)

    def on_spbtn_offs_angle_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_offs_angle", gtkspinbutton, data)

    # Y+Y+
    @ensure_errors_dismissed
    def on_angle_yp_released(self, gtkbutton, data=None):
        self.stat.poll()
        xstart = (
            self.stat.position[0]
            - self.stat.g5x_offset[0]
            - self.stat.g92_offset[0]
            - self.stat.tool_offset[0]
        )
        # move Y - xy_clearance
        s = """%s
        G91
        G1 Y-%f
        G90""" % (
            self.setunits, self.halcomp["ps_xy_clearance"]
        )
        if self.gcode(s) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_yplus.ngc
        if self.ocode("o<psng_yplus> call") == -1:
            return
        # Calculate Y result
        a = self.probed_position_with_offsets("yplus")
        ycres = float(a[1]) + 0.5 * self.halcomp["ps_probe_diam"]

        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        # move X + edge_length
        s = """%s
        G91
        G1 X%f
        G90""" % (
            self.setunits, self.halcomp["ps_edge_length"]
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_yplus.ngc
        if self.ocode("o<psng_yplus> call") == -1:
            return
        # Calculate Y result
        a = self.probed_position_with_offsets("yplus")
        ypres = float(a[1]) + 0.5 * self.halcomp["ps_probe_diam"]
        alfa = math.degrees(math.atan2(ypres - ycres, self.halcomp["ps_edge_length"]))

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "YcYpA",
            yc=ycres,
            yp=ypres,
            a=alfa,
        )

        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        # move XY to adj start point
        s = "G1 X%f Y%f" % (xstart, ycres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.rotate_coord_system(alfa)

    # Y-Y-
    @ensure_errors_dismissed
    def on_angle_ym_released(self, gtkbutton, data=None):
        self.stat.poll()
        xstart = (
            self.stat.position[0]
            - self.stat.g5x_offset[0]
            - self.stat.g92_offset[0]
            - self.stat.tool_offset[0]
        )
        # move Y + xy_clearance
        s = """%s
        G91
        G1 Y%f
        G90""" % (
            self.setunits, self.halcomp["ps_xy_clearance"]
        )
        if self.gcode(s) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_yminus.ngc
        if self.ocode("o<psng_yminus> call") == -1:
            return
        # Calculate Y result
        a = self.probed_position_with_offsets("yminus")
        ycres = float(a[1]) - 0.5 * self.halcomp["ps_probe_diam"]

        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        # move X - edge_length
        s = """%s
        G91
        G1 X-%f
        G90""" % (
            self.setunits, self.halcomp["ps_edge_length"]
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_yminus.ngc
        if self.ocode("o<psng_yminus> call") == -1:
            return
        # Calculate Y result
        a = self.probed_position_with_offsets("yminus")
        ymres = float(a[1]) - 0.5 * self.halcomp["ps_probe_diam"]
        alfa = math.degrees(math.atan2(ycres - ymres, self.halcomp["ps_edge_length"]))

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "YmYcA",
            ym=ymres,
            yc=ycres,
            a=alfa,
        )
        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        # move XY to adj start point
        s = "G1 X%f Y%f" % (xstart, ycres)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.rotate_coord_system(alfa)

    # X+X+
    @ensure_errors_dismissed
    def on_angle_xp_released(self, gtkbutton, data=None):
        self.stat.poll()
        ystart = (
            self.stat.position[1]
            - self.stat.g5x_offset[1]
            - self.stat.g92_offset[1]
            - self.stat.tool_offset[1]
        )
        # move X - xy_clearance
        s = """%s
        G91
        G1 X-%f
        G90""" % (
            self.setunits, self.halcomp["ps_xy_clearance"]
        )
        if self.gcode(s) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xplus.ngc
        if self.ocode("o<psng_xplus> call") == -1:
            return
        # Calculate X result
        a = self.probed_position_with_offsets("xplus")
        xcres = float(a[0]) + 0.5 * self.halcomp["ps_probe_diam"]

        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        # move Y - edge_length
        s = """%s
        G91
        G1 Y-%f
        G90""" % (
            self.setunits, self.halcomp["ps_edge_length"]
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xplus.ngc
        if self.ocode("o<psng_xplus> call") == -1:
            return
        # Calculate X result
        a = self.probed_position_with_offsets("xplus")
        xpres = float(a[0]) + 0.5 * self.halcomp["ps_probe_diam"]
        alfa = math.degrees(math.atan2(xcres - xpres, self.halcomp["ps_edge_length"]))

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XcXpA",
            xc=xcres,
            xp=xpres,
            a=alfa,
        )
        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        # move XY to adj start point
        s = "G1 X%f Y%f" % (xcres, ystart)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.rotate_coord_system(alfa)

    # X-X-
    @ensure_errors_dismissed
    def on_angle_xm_released(self, gtkbutton, data=None):
        self.stat.poll()
        ystart = (
            self.stat.position[1]
            - self.stat.g5x_offset[1]
            - self.stat.g92_offset[1]
            - self.stat.tool_offset[1]
        )
        # move X + xy_clearance
        s = """%s
        G91
        G1 X%f
        G90""" % (
            self.setunits, self.halcomp["ps_xy_clearance"]
        )
        if self.gcode(s) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xminus.ngc
        if self.ocode("o<psng_xminus> call") == -1:
            return
        # Calculate X result
        a = self.probed_position_with_offsets("xminus")
        xcres = float(a[0]) - 0.5 * self.halcomp["ps_probe_diam"]

        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        # move Y + edge_length
        s = """%s
        G91
        G1 Y%f
        G90""" % (
            self.setunits, self.halcomp["ps_edge_length"]
        )
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start psng_xminus.ngc
        if self.ocode("o<psng_xminus> call") == -1:
            return
        # show X result
        a = self.probed_position_with_offsets("xminus")
        xmres = float(a[0]) - 0.5 * self.halcomp["ps_probe_diam"]
        alfa = math.degrees(math.atan2(xcres - xmres, self.halcomp["ps_edge_length"]))

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XmXcA",
            xm=xmres,
            xc=xcres,
            a=alfa,
        )
        # move Z to start point
        if self.z_clearance_up() == -1:
            return
        # move XY to adj start point
        s = "G1 X%f Y%f" % (xcres, ystart)
        if self.gcode(s, self.halcomp["ps_edge_length"]) == -1:
            return
        self.rotate_coord_system(alfa)

    # Hole2 Center: Xin- Xin+ Yin- Yin+; and calculate Angle relative to (0;0)
    @ensure_errors_dismissed
    def on_btn_rot_hole2_released(self, gtkbutton, data=None):
		# Center: Xin- Xin+ Yin- Yin+ 
        self.on_xy_hole_released(gtkbutton)
        if self.error_poll() == -1:
            return 
        self.stat.poll()

        x_hole2 = (
            self.stat.position[0]
            - self.stat.g5x_offset[0]
            - self.stat.g92_offset[0]
            - self.stat.tool_offset[0]
        )
        y_hole2 = (
            self.stat.position[1]
            - self.stat.g5x_offset[1]
            - self.stat.g92_offset[1]
            - self.stat.tool_offset[1]
        )
        dist_to_hole2 = math.sqrt(x_hole2*x_hole2 + y_hole2*y_hole2)
        alfa = math.degrees(math.atan2(y_hole2,x_hole2))
        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XcYcA",
            xc=x_hole2,
            yc=y_hole2,
            a=alfa,
        )
#       rotate coord system (alfa)  
        self.spbtn_offs_angle.set_value(alfa)
        self._h_probe_a = alfa

        s = "G10 L2 P0"
        s += " X%s" % x_hole2
        s += " Y%s" % y_hole2
        s += " R%s" % alfa
        self.gcode(s)
        s = "G10 L20 P0"
        s += " X%s" % dist_to_hole2
        s += " Y0"
        self.gcode(s)
        self.vcp_reload()
        time.sleep(1)
        
    # --------------
    # Helper Methods
    # --------------
    def rotate_coord_system(self, a=0.0):
        self.spbtn_offs_angle.set_value(a)
        self._h_probe_a = a

        if self.chk_auto_rott.get_active():
            s = "G10 L2 P0"
            if self.halcomp["chk_set_zero"]:
                s += " X%s" % self.halcomp["ps_offs_x"]
                s += " Y%s" % self.halcomp["ps_offs_y"]
            else:
                self.stat.poll()
                x = self.stat.position[0]
                y = self.stat.position[1]
                s += " X%s" % x
                s += " Y%s" % y
            s += " R%s" % a
            self.gcode(s)
            self.vcp_reload()
            time.sleep(1)


    # -----------------
    # Zero (Touch Off) Buttons
    # -----------------
    def on_chk_set_zero_toggled(self, gtkcheckbutton, data=None):
        self.halcomp["chk_set_zero"] = gtkcheckbutton.get_active()
        self.hal_led_set_zero.hal_pin.set(gtkcheckbutton.get_active())
        self.prefs.putpref("chk_set_zero", gtkcheckbutton.get_active(), bool)

    def on_spbtn_offs_x_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_offs_x", gtkspinbutton, data)

    def on_spbtn_offs_x_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_offs_x", gtkspinbutton, data)

    def on_btn_set_x_released(self, gtkbutton, data=None):
        self.prefs.putpref("ps_offs_x", self.spbtn_offs_x.get_value(), float)
        self.gcode("G10 L20 P0 X%f" % self.spbtn_offs_x.get_value())
        self.vcp_reload()

    def on_spbtn_offs_y_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_offs_y", gtkspinbutton, data)

    def on_spbtn_offs_y_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_offs_y", gtkspinbutton, data)

    def on_btn_set_y_released(self, gtkbutton, data=None):
        self.prefs.putpref("ps_offs_y", self.spbtn_offs_y.get_value(), float)
        self.gcode("G10 L20 P0 Y%f" % self.spbtn_offs_y.get_value())
        self.vcp_reload()

    def on_spbtn_offs_z_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_offs_z", gtkspinbutton, data)

    def on_spbtn_offs_z_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_offs_z", gtkspinbutton, data)

    def on_btn_set_z_released(self, gtkbutton, data=None):
        self.prefs.putpref("ps_offs_z", self.spbtn_offs_z.get_value(), float)
        self.gcode("G10 L20 P0 Z%f" % self.spbtn_offs_z.get_value())
        self.vcp_reload()



    # -----------------
    # Arm Buttons
    # -----------------
    def on_chk_arm_enable_toggled(self, gtkcheckbutton, data=None):
        self.halcomp["chk_arm_enable"] = gtkcheckbutton.get_active()
        self.hal_led_arm_enable.hal_pin.set(gtkcheckbutton.get_active())
        self.prefs.putpref("chk_arm_enable", gtkcheckbutton.get_active(), bool)
        if gtkcheckbutton.get_active():
            self.spbtn_arm_delta_x.set_sensitive( True )
            self.spbtn_arm_delta_y.set_sensitive( True )
            self.btn_arm_is_zero.set_sensitive( True )
            self.btn_spindle_is_zero.set_sensitive( True )
        else:
            self.spbtn_arm_delta_x.set_sensitive( False )
            self.spbtn_arm_delta_y.set_sensitive( False )
            self.btn_arm_is_zero.set_sensitive( False )
            self.btn_spindle_is_zero.set_sensitive( False )            

    def on_spbtn_arm_delta_x_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_arm_delta_x", gtkspinbutton, data)

    def on_spbtn_arm_delta_x_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_arm_delta_x", gtkspinbutton, data)

    def on_spbtn_arm_delta_y_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("ps_arm_delta_y", gtkspinbutton, data)

    def on_spbtn_arm_delta_y_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("ps_arm_delta_y", gtkspinbutton, data)


    def on_btn_arm_is_zero_released(self, gtkbutton, data=None):
        self.stat.poll()
        tmpx = (
            self.stat.position[0]
#            - self.stat.g5x_offset[0]
#            - self.stat.g92_offset[0]
#            - self.stat.tool_offset[0]
        )
        tmpy = (
            self.stat.position[1]
#            - self.stat.g5x_offset[1]
#            - self.stat.g92_offset[1]
#            - self.stat.tool_offset[1]
        )
        self.gcode("G10 L2 P0 X%f Y%f" % (tmpx + self.halcomp["ps_arm_delta_x"],tmpy + self.halcomp["ps_arm_delta_y"]))


    def on_btn_spindle_is_zero_released(self, gtkbutton, data=None):
        self.stat.poll()
        tmpx = (
            self.stat.position[0]
#            - self.stat.g5x_offset[0]
#            - self.stat.g92_offset[0]
#            - self.stat.tool_offset[0]
        )
        tmpy = (
            self.stat.position[1]
#            - self.stat.g5x_offset[1]
#            - self.stat.g92_offset[1]
#            - self.stat.tool_offset[1]
        )
        self.gcode("G10 L2 P0 X%f Y%f" % (tmpx,tmpy))



    # -----------
    # JOG METODS
    # -----------
    def _make_jog_increments(self):
        self.incr_rbt_dic = {}

        # We get the increments from INI File
        if len(self.jog_increments) > 10:
            LOG.warning(_("To many increments given in INI file for this screen. "
            "Only the first 10 will be reachable through this screen."))
            # we shorten the increment list to 10 (first is default = 0)
            self.jog_increments = self.jog_increments[0:11]

        # The first radio button is created to get a radio button group
        # The group is called according the name off  the first button
        # We use the pressed signal, not the toggled, otherwise two signals will be emitted
        # One from the released button and one from the pressed button
        # we make a list of the buttons to later add the hardware pins to them
        label = _("Continuous")
        rbt = Gtk.RadioButton(label = label)
        rbt.set_property("name","rbt_0")
        rbt.connect("pressed", self._jog_increment_changed)
        self.widgets.vbtb_jog_incr.pack_start(rbt, True, True, 0)
        rbt.set_property("draw_indicator", False)
        rbt.show()
        self.incr_rbt_dic[rbt.get_property("name")] = rbt
        # the rest of the buttons are now added to the group
        # self.no_increments is set while setting the hal pins with self._check_len_increments
        for item in range(1, len(self.jog_increments)):
            name = "rbt_{0}".format(item)
            rbt = Gtk.RadioButton.new_from_widget(self.incr_rbt_dic["rbt_0"])
            rbt.set_label(label = self.jog_increments[item])
            rbt.set_property("name",name)
            rbt.connect("pressed", self._jog_increment_changed)
            self.widgets.vbtb_jog_incr.pack_start(rbt, True, True, 0)
            rbt.set_property("draw_indicator", False)
            rbt.show()
            self.incr_rbt_dic[rbt.get_property("name")] = rbt
        self.incr_rbt_dic["rbt_0"].set_active(True)
        self.active_increment = "rbt_0"
        # Set name to assign CSS
        self.widgets.vbtb_jog_incr.set_property("name","jog_incr_buttons")



    def _init_jog_increments(self):
        self.incr_rbt_dic = {}
        # Get the increments from INI File
        jog_increments = []
        increments = self.inifile.find("DISPLAY", "INCREMENTS")
        if increments:
            if "," in increments:
                for i in increments.split(","):
                    jog_increments.append(i.strip())
            else:
                jog_increments = increments.split()
            jog_increments.insert(0, 0)
        else:
            jog_increments = [0, "1,000", "0,100", "0,010", "0,001"]
            print(
                "**** PROBE SCREEN INFO **** \n No default jog increments entry found in [DISPLAY] of INI file"
            )

        self.jog_increments = jog_increments
        if len(self.jog_increments) > 5:
            print(_("**** PROBE SCREEN INFO ****"))
            print(_("**** To many increments given in INI File for this screen ****"))
            print(_("**** Only the first 5 will be reachable through this screen ****"))
            # we shorten the incrementlist to 5 (first is default = 0)
            self.jog_increments = self.jog_increments[0:5]

        # The first radio button is created to get a radio button group
        # The group is called according the name off  the first button
        # We use the pressed signal, not the toggled, otherwise two signals will be emitted
        # One from the released button and one from the pressed button
        # we make a list of the buttons to later add the hardware pins to them
        label = "Cont"
        rbt0 = Gtk.RadioButton(label = label)
        rbt0.set_property("name","rbt_0")
        rbt0.connect("pressed", self.on_increment_changed, 0)
        self.steps.pack_start(rbt0, True, True, 0)
        rbt0.set_property("draw_indicator", False)
        rbt0.show()
        self.incr_rbt_dic[rbt0.get_property("name")] = rbt0
        # the rest of the buttons are now added to the group
        # self.no_increments is set while setting the hal pins with self._check_len_increments
        for item in range(1, len(self.jog_increments)):
            name = "rbt_{0}".format(item)
            rbt = Gtk.RadioButton.new_from_widget(self.incr_rbt_dic["rbt_0"])
            rbt.set_label(label = self.jog_increments[item])
            rbt.set_property("name",name)
            rbt.connect("pressed", self.on_increment_changed, self.jog_increments[item])
            self.steps.pack_start(rbt, True, True, 0)
            rbt.set_property("draw_indicator", False)
            rbt.show()
            self.incr_rbt_dic[rbt.get_property("name")] = rbt
        self.incr_rbt_dic["rbt_0"].set_active(True)
        self.active_increment = "rbt_0"

    # -----------
    # JOG BUTTONS
    # -----------
    def on_increment_changed(self, widget=None, data=None):
        if data == 0:
            self.distance = 0
        else:
            self.distance = self._parse_increment(data)
        self.halcomp["jog-increment"] = self.distance
        self.active_increment =  widget.get_property("name")

    def _from_internal_linear_unit(self, v, unit=None):
        if unit is None:
            unit = self.stat.linear_units
        lu = (unit or 1) * 25.4
        return v * lu

    def _parse_increment(self, jogincr):
        if jogincr.endswith("mm"):
            scale = self._from_internal_linear_unit(1 / 25.4)
        elif jogincr.endswith("cm"):
            scale = self._from_internal_linear_unit(10 / 25.4)
        elif jogincr.endswith("um"):
            scale = self._from_internal_linear_unit(0.001 / 25.4)
        elif jogincr.endswith("in") or jogincr.endswith("inch"):
            scale = self._from_internal_linear_unit(1.0)
        elif jogincr.endswith("mil"):
            scale = self._from_internal_linear_unit(0.001)
        else:
            scale = 1
        jogincr = jogincr.rstrip(" inchmuil")
        if "/" in jogincr:
            p, q = jogincr.split("/")
            jogincr = float(p) / float(q)
        else:
            jogincr = float(jogincr)
        return jogincr * scale

    def on_btn_jog_pressed(self, widget, data=None):
        # only in manual mode we will allow jogging the axis at this development state
        if not self.stat.task_mode == linuxcnc.MODE_MANUAL:
          self.command.mode(linuxcnc.MODE_MANUAL)
          self.command.wait_complete()
          self.stat.poll()
          if not self.stat.task_mode == linuxcnc.MODE_MANUAL:
            return

        axisletter = widget.get_label()[0]
        if not axisletter.lower() in "xyzabcuvw":
            print("unknown axis %s" % axisletter)
            return

        # get the axisnumber
        axisnumber = "xyzabcuvws".index(axisletter.lower())

        # if data = True, then the user pressed SHIFT for Jogging and
        # want's to jog at 0.2 speed
        if data:
            value = 0.2
        else:
            value = 1

        velocity = float(self.inifile.find("TRAJ", "DEFAULT_LINEAR_VELOCITY"))

        dir = widget.get_label()[1]
        if dir == "+":
            direction = 1
        else:
            direction = -1

        self.command.teleop_enable(1)
        if self.distance != 0:  # incremental jogging
            self.command.jog(
                linuxcnc.JOG_INCREMENT,
                False,
                axisnumber,
                direction * velocity,
                self.distance,
            )
        else:  # continuous jogging
            self.command.jog(
                linuxcnc.JOG_CONTINUOUS, False, axisnumber, direction * velocity
            )

    def on_btn_jog_released(self, widget, data=None):
        axisletter = widget.get_label()[0]
        if not axisletter.lower() in "xyzabcuvw":
            print("unknown axis %s" % axisletter)
            return

        axis = "xyzabcuvw".index(axisletter.lower())

        self.command.teleop_enable(1)
        if self.distance != 0:
            pass
        else:
            self.command.jog(linuxcnc.JOG_STOP, False, axis)
   
    # -----------
    # DIAGONAL JOG 
    # -----------
    def on_XminusYplus_jog_pressed(self, widget, data=None):
        self.on_btn_jog_pressed(self.jog_Xminus_btn)
        self.on_btn_jog_pressed(self.jog_Yplus_btn)
        
    def on_XminusYplus_jog_released(self, widget, data=None):
        self.on_btn_jog_released(self.jog_Xminus_btn)
        self.on_btn_jog_released(self.jog_Yplus_btn)
        
    def on_XminusYminus_jog_pressed(self, widget, data=None):
        self.on_btn_jog_pressed(self.jog_Xminus_btn)
        self.on_btn_jog_pressed(self.jog_Yminus_btn)
        
    def on_XminusYminus_jog_released(self, widget, data=None):
        self.on_btn_jog_released(self.jog_Xminus_btn)
        self.on_btn_jog_released(self.jog_Yminus_btn)
        
    def on_XplusYplus_jog_pressed(self, widget, data=None):
        self.on_btn_jog_pressed(self.jog_Xplus_btn)
        self.on_btn_jog_pressed(self.jog_Yplus_btn)
        
    def on_XplusYplus_jog_released(self, widget, data=None):
        self.on_btn_jog_released(self.jog_Xplus_btn)
        self.on_btn_jog_released(self.jog_Yplus_btn)
        
    def on_XplusYminus_jog_pressed(self, widget, data=None):
        self.on_btn_jog_pressed(self.jog_Xplus_btn)
        self.on_btn_jog_pressed(self.jog_Yminus_btn)
        
    def on_XplusYminus_jog_released(self, widget, data=None):
        self.on_btn_jog_released(self.jog_Xplus_btn)
        self.on_btn_jog_released(self.jog_Yminus_btn)
        



    # ----------------
    # Remap M6 Buttons
    # ----------------

    # Spinbox for setter height with autosave value inside machine pref file
    def on_spbtn_setter_height_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("setterheight", gtkspinbutton, data)

    def on_spbtn_setter_height_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("setterheight", gtkspinbutton, data)

        # Record results to history panel
        c = "TS Height = " + "%.4f" % gtkspinbutton.get_value()
        self.add_history_text(c)

    # Spinbox for block height with autosave value inside machine pref file
    def on_spbtn_block_height_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("blockheight", gtkspinbutton, data)

    def on_spbtn_block_height_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("blockheight", gtkspinbutton, data)

        # set coordinate system to new origin
        self.gcode("G10 L2 P0 Z%s" % gtkspinbutton.get_value())
        self.vcp_reload()

        # Record results to history panel
        c = "Workpiece Height = " + "%.4f" % gtkspinbutton.get_value()
        self.add_history_text(c)

    def on_chk_enbl_remap_m6_toggled( self, gtkcheckbutton, data = None ):
        if gtkcheckbutton.get_active():
            self.btn_probe_tool_setter.set_sensitive( True )
            self.btn_probe_workpiece.set_sensitive( True )
            self.spbtn_setter_height.set_sensitive( True )
            self.spbtn_block_height.set_sensitive( True )
            self.label_probe_workpiece.set_sensitive( True )
            self.label_probe_tool_setter.set_sensitive( True )           
            self.halcomp["enbl_remap_m6"] = True
            self.hal_led_enbl_remap_m6.hal_pin.set(1)
        else:
            self.btn_probe_tool_setter.set_sensitive( False )
            self.btn_probe_workpiece.set_sensitive( False  )
            self.spbtn_setter_height.set_sensitive( False  )
            self.spbtn_block_height.set_sensitive( False  )
            self.label_probe_workpiece.set_sensitive( False  )
            self.label_probe_tool_setter.set_sensitive( False  )           
            self.halcomp["enbl_remap_m6"] = False 
            self.hal_led_enbl_remap_m6.hal_pin.set(0)
            
        self.prefs.putpref( "enbl_remap_m6", gtkcheckbutton.get_active(), bool )


    #---------------------------
    # Remap M6 metods
    #---------------------------

    # Read the ini file config [TOOLSENSOR] section
    def _init_tool_sensor_data(self):
        xpos = self.inifile.find("TOOLSENSOR", "X")
        ypos = self.inifile.find("TOOLSENSOR", "Y")
        zpos = self.inifile.find("TOOLSENSOR", "Z")
        maxprobe = self.inifile.find("TOOLSENSOR", "MAXPROBE")
        tsdiam = self.inifile.find("TOOLSENSOR", "TS_DIAMETER")
        ps_rapid_speed = self.inifile.find("TOOLSENSOR", "RAPID_SPEED")

        if (
            xpos is None
            or ypos is None
            or zpos is None
            or maxprobe is None
            or tsdiam is None
            or ps_rapid_speed is None
        ):
            self.btn_tool_dia.set_sensitive(False)
            self.btn_probe_tool_setter.set_sensitive(False)
            self.chk_enbl_remap_m6.set_active(False)
            
            self.error_dialog(
                "Invalid INI Configuration",
                secondary="Please check the TOOLSENSOR INI configurations",
            )
        else:
            self.xpos = float(xpos)
            self.ypos = float(ypos)
            self.zpos = float(zpos)
            self.maxprobe = float(maxprobe)
            self.tsdiam = float(tsdiam)
            self.ps_rapid_speed = float(ps_rapid_speed)



    # Down probe to table for measuring it and use for calculate tool setter height and can set G10 L20 Z0 if you tick auto zero
    # Z-
    @ensure_errors_dismissed
    def on_btn_probe_table_released(self, gtkbutton, data=None):
        # Start psng_probe_table.ngc
        if self.ocode("o<psng_probe_table> call") == -1:
            return
        a = self.probed_position_with_offsets("zminus")
        self.add_history(gtkbutton.get_tooltip_text(), "Z", z=a[2])
        self.set_zerro("Z", 0, 0, a[2])

    # Down probe to tool setter for measuring it vs table probing result
    @ensure_errors_dismissed
    def on_btn_probe_tool_setter_released(self, gtkbutton, data=None):
        # Start psng_probe_tool_setter.ngc
        if self.ocode("o<psng_probe_tool_setter> call") == -1:
            return
#        self.vcp_reload()
        # self.stat.linear_units will return machine units: 1.0 for metric and 1/25,4 for imperial
        # self.halcomp["ps_metric_mode"] is display units
        factor=1
        if self.halcomp["ps_metric_mode"] != int(self.stat.linear_units):
            if self.halcomp["ps_metric_mode"]:
                factor = 25.4
            else:
                factor = (1.0 / 25.4)
        a = self.stat.probed_position
        self.spbtn_setter_height.set_value(float(a[2])*factor)
        self.add_history(gtkbutton.get_tooltip_text(), "Z", z=a[2])
        direction=-1
        extra_travel=0
        if self.chk_signal_delay.get_active():
            if self.chk_use_fine.get_active():
                extra_travel = self.spbtn1_probe_vel.get_value() * self.spbtn_signal_delay.get_value() * direction / 60000
            else:
                extra_travel = self.spbtn1_search_vel.get_value() * self.spbtn_signal_delay.get_value() * direction / 60000
        self.spbtn_setter_height.set_value(float(a[2]) - extra_travel)
        self.label_val_overmove.set_text( " = %.5f" % extra_travel )            

    # Down probe to workpiece for measuring it vs Know tool setter height
    @ensure_errors_dismissed
    def on_btn_probe_workpiece_released(self, gtkbutton, data=None):
        # Start psng_probe_workpiece.ngc
        if self.ocode("o<psng_probe_workpiece> call") == -1:
            return
#        self.vcp_reload()
        # self.stat.linear_units will return machine units: 1.0 for metric and 1/25,4 for imperial
        # self.halcomp["ps_metric_mode"] is display units
        factor=1
        if self.halcomp["ps_metric_mode"] != int(self.stat.linear_units):
            if self.halcomp["ps_metric_mode"]:
                factor = 25.4
            else:
                factor = (1.0 / 25.4)
        a = self.stat.probed_position 
        self.spbtn_block_height.set_value(float(a[2])*factor)
        self.add_history(gtkbutton.get_tooltip_text(), "Z", z=a[2])
        direction=-1
        extra_travel=0
        if self.chk_signal_delay.get_active():
            if self.chk_use_fine.get_active():
                extra_travel = self.spbtn1_probe_vel.get_value() * self.spbtn_signal_delay.get_value() * direction / 60000
            else:
                extra_travel = self.spbtn1_search_vel.get_value() * self.spbtn_signal_delay.get_value() * direction / 60000
        self.spbtn_block_height.set_value(float(a[2]) - extra_travel)
        self.label_val_overmove.set_text( " = %.5f" % extra_travel )            

    # Probe tool Diameter
    @ensure_errors_dismissed
    def on_btn_tool_dia_released(self, gtkbutton, data=None):
        # move XY to Tool Setter point
        # with psng_tool_diameter.ngc
        if self.ocode("o<psng_tool_diameter> call") == -1:
            return
        # move X - edge_length- xy_clearance
        s = """%s
        G91
        G1 X-%f
        G90""" % (
            self.setunits, 
            0.5 * self.tsdiam + self.halcomp["ps_xy_clearance"]
        )
        if self.gcode(s) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start xplus.ngc
        if self.ocode("o<psng_xplus> call") == -1:
            return
        # show X result
        a = self.probed_position_with_offsets("xplus")
        xpres = float(a[0]) + 0.5 * self.halcomp["ps_probe_diam"]

        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # move to finded  point X
        s = "G1 X%f" % xpres
        if self.gcode(s) == -1:
            return

        # move X + tsdiam +  xy_clearance
        aa = self.tsdiam + self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 X%f
        G90""" % (
            self.setunits, 
            aa
        )
        if self.gcode(s) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start xminus.ngc

        if self.ocode("o<psng_xminus> call") == -1:
            return
        # Calculate X result
        a = self.probed_position_with_offsets("xminus")
        xmres = float(a[0]) - 0.5 * self.halcomp["ps_probe_diam"]
        xcres = 0.5 * (xpres + xmres)
        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # go to the new center of X
        s = "G1 X%f" % xcres
        if self.gcode(s) == -1:
            return

        # move Y - tsdiam/2 - xy_clearance
        a = 0.5 * self.tsdiam + self.halcomp["ps_xy_clearance"]
        s = """%s
            G91
        G1 Y-%f
        G90""" % (
            self.setunits,
            a
        )
        if self.gcode(s) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start yplus.ngc
        if self.ocode("o<psng_yplus> call") == -1:
            return
        # Calculate Y result
        a = self.probed_position_with_offsets("yplus")
        ypres = float(a[1]) + 0.5 * self.halcomp["ps_probe_diam"]
        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        # move to finded  point Y
        s = "G1 Y%f" % ypres
        if self.gcode(s) == -1:
            return

        # move Y + tsdiam +  xy_clearance
        aa = self.tsdiam + self.halcomp["ps_xy_clearance"]
        s = """%s
        G91
        G1 Y%f
        G90""" % (
            self.setunits, 
            aa
        )
        if self.gcode(s) == -1:
            return
        if self.z_clearance_down() == -1:
            return
        # Start xminus.ngc
        if self.ocode("o<psng_yminus> call") == -1:
            return
        # Calculate Y result
        a = self.probed_position_with_offsets("yminus")
        ymres = float(a[1]) - 0.5 * self.halcomp["ps_probe_diam"]

        # find, show and move to finded  point
        ycres = 0.5 * (ypres + ymres)
        diam = self.halcomp["ps_probe_diam"] + (ymres - ypres - self.tsdiam)

        # move Z to start point up
        if self.z_clearance_up() == -1:
            return
        self.stat.poll()
        tmpz = self.stat.position[2] - 4
        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XcYcZD",
            xc=xcres,
            yc=ycres,
            z=tmpz,
            d=diam,
        )
        # move to finded  point
        s = "G1 Y%f M5" % ycres
        if self.gcode(s) == -1:
            return

    # Here we create a manual tool change dialog
    def on_tool_change(self, gtkbutton, data=None):
        change = self.halcomp["toolchange-change"]
        toolnumber = self.halcomp["toolchange-number"]
        toolprepnumber = self.halcomp["toolchange-prep-number"]
        print("tool-number =", toolnumber)
        print("tool_prep_number =", toolprepnumber, change)
        if change:
            # if toolprepnumber = 0 we will get an error because we will not be able to get
            # any tooldescription, so we avoid that case
            if toolprepnumber == 0:
                message = _("Please remove the mounted tool and press OK when done")
            else:
                tooltable = self.inifile.find("EMCIO", "TOOL_TABLE")
                if not tooltable:
                    self.error_dialog(
                        "Tool Measurement Error",
                        secondary="Did not find a toolfile file in [EMCIO] TOOL_TABLE",
                    )
                CONFIGPATH = os.environ["CONFIG_DIR"]
                toolfile = os.path.join(CONFIGPATH, tooltable)
                self.tooledit1.set_filename(toolfile)
                tooldescr = self.tooledit1.get_toolinfo(toolprepnumber)[16]
                message = _(
                    "Please change to tool\n\n# {0:d}     {1}\n\n then click OK."
                ).format(toolprepnumber, tooldescr)
            result = self.warning_dialog(message, title=_("Manual Toolchange"))
            print("result = ", result)
            if result:
#                self.vcp_reload() can cause a hang-up issue during tool change and OK button presses
                self.halcomp["toolchange-changed"] = True
            else:
                print(
                    "toolchange abort",
                    toolnumber,
                    self.halcomp["toolchange-prep-number"],
                )
                self.command.abort()
                self.halcomp["toolchange-prep-number"] = toolnumber
                self.halcomp["toolchange-change"] = False
                self.halcomp["toolchange-changed"] = True
                message = _("**** TOOLCHANGE ABORTED ****")
                self.warning_dialog(message)
        else:
            self.halcomp["toolchange-changed"] = False

def get_handlers(halcomp,builder,useropts):
    return [ProbeScreen(halcomp,builder,useropts)]
