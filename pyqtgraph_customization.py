"""
/***************************************************************************
        ValueTool           PyQtGraph Customization
                            -------------------
        begin               : 2014-06-16
        copyright           : (C) 2014 by Werner Macho
        email               : werner.macho@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import pyqtgraph as pg
import time


class DateTimeAxis(pg.AxisItem):

    time_enabled = False

    def setTimeEnabled(self, timeEnabled):
        self.time_enabled = timeEnabled

    # def tickValues(self, min, max, size):
    #     # min is the start of the range in seconds
    #     # max is the end of the range in secods
    #     # what is size?
    #     range = max - min
    #     majSpacing = 3600 * 24
    #     minSpacing = majSpacing / 4
    #     return [
    #         (majSpacing, []),  # TODO write the correct values here
    #         (minSpacing, [])]

    def tickStrings(self, values, scale, spacing):
        if self.time_enabled:
            strns = []
            timerange = max(values)-min(values)
            #if rng < 120:
            #    return pg.AxisItem.tickStrings(self, values, scale, spacing)
            if timerange < 3600*24:
                string = '%H:%M:%S'
                label1 = '%b %d  %Y -'
                label2 = ' %b %d, %Y'
            elif 3600*24 <= timerange < 3600*24*30:
                string = '%d %H:%M'
                label1 = '%b - '
                label2 = '%b, %Y'
            elif 3600*24*30 <= timerange < 3600*24*30*24:
                string = '%b %y'
                label1 = '%Y -'
                label2 = ' %Y'
            elif timerange >= 3600*24*30*24:
                string = '%Y'
                label1 = ''
                label2 = ''
            for x in values:
                try:
                    strns.append(time.strftime(string, time.localtime(x)))
                except ValueError:  # Windows can't handle dates before 1970
                    strns.append('')
            try:
                #label = time.strftime(label1, time.localtime(min(
                # values)))+time.strftime(label2, time.localtime(max(values)))
                label = time.strftime(label1, time.localtime(min(values)))
            except ValueError:
                label = ''
            self.setLabel(text=label)
            return strns
        else:
            strns = []
            for val in values:
                try:
                    strns.append('%.0f' % val)
                except ValueError:  # Windows can't handle dates before 1970
                    strns.append('')
            self.setLabel(text='')
            return strns


class DateTimeViewBox(pg.ViewBox):
    pass
    # def __init__(self, *args, **kwds):
    #     pg.ViewBox.__init__(self, *args, **kwds)
    #     self.setMouseMode(self.RectMode)
    #
    # ## reimplement right-click to zoom out
    # def mouseClickEvent(self, ev):
    #     if ev.button() == QtCore.Qt.RightButton:
    #         self.autoRange()
    #
    # def mouseDragEvent(self, ev):
    #     if ev.button() == QtCore.Qt.RightButton:
    #         ev.ignore()
    #     else:
    #         pg.ViewBox.mouseDragEvent(self, ev)