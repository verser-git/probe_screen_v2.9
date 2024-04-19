# Notes for DISPLAY = axis

By default, the Probe Screen doesn't fit in 1280x1024 screen a bit, so add to beginning of .axisrc to expand the area

   ```sh
root_window.tk.call("wm","geometry",".","1280x1024")
#root_window.attributes("-fullscreen",1)

root_window.tk.call('.pane.top.tabs','configure','-width',20)
root_window.tk.call('.pane.top.feedoverride','configure','-width',20)
root_window.tk.call('.pane.top.rapidoverride','configure','-width',20)
root_window.tk.call('.pane.top.spinoverride','configure','-width',20)
root_window.tk.call('.pane.top.jogspeed.l0','configure','-text','Jog V')
#root_window.tk.call('.pane.top.ajogspeed.l0','configure','-text','Jog A')
root_window.tk.call('.pane.top.maxvel.l0','configure','-text','Max V')
   ```
