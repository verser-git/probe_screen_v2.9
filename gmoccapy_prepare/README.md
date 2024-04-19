# Notes for DISPLAY = gmoccapy

Gmoccapy intercepts MANUAL-MDI-AUTO mode switching events and closes the Probe Screen.
To avoid this, editing with root rights of the system file /usr/bin/gmoccapy is required.
It is necessary to add the following lines in three places

   ```sh
        if self.widgets.tbtn_user_tabs.get_active():
            return
   ```


1.
   ```sh
    def on_hal_status_mode_manual(self, widget):
        print ("MANUAL Mode")
        self.widgets.rbt_manual.set_active(True)
        # if setup page is activated, we must leave here, otherwise the pages will be reset
        if self.widgets.tbtn_setup.get_active():
            return
        if self.widgets.tbtn_user_tabs.get_active():
            return
    ...
   ```
2.
   ```sh
    def on_hal_status_mode_mdi(self, widget):
        print ("MDI Mode", self.tool_change)
        # if the edit offsets button is active, we do not want to change
        # pages, as the user may want to edit several axis values
        if self.touch_button_dic["edit_offsets"].get_active():
            return

        # self.tool_change is set only if the tool change was commanded
        # from tooledit widget/page, so we do not want to switch the
        # screen layout to MDI, but set the manual widgets
        if self.tool_change:
            self.widgets.ntb_main.set_current_page(0)
            self.widgets.ntb_button.set_current_page(_BB_MANUAL)
            self.widgets.ntb_info.set_current_page(0)
            self.widgets.ntb_jog.set_current_page(0)
            return

        if self.widgets.tbtn_user_tabs.get_active():
            return
    ...
   ```
3.
   ```sh
    def on_hal_status_mode_auto(self, widget):
        print ("AUTO Mode")
        if self.widgets.tbtn_user_tabs.get_active():
            return
    ...
   ```

This is not an ideal solution. As a result, you will need to press the mode buttons on the right once again when exiting the Probe Screen.
If more competent proposals come, I will immediately apply them.
The folder contains the already fixed gmoccapy v3.1.3.8 file, which comes with the liveCD