"""
/***************************************************************************
        ValueTool           applyfilter
                            -------------------
        begin               : 2014-10-15
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


class ApplyFilter:

    def __init__(self, parent, canvas):
        self.parent = parent
        self.canvas = canvas

    def smooth(self, orig_x, orig_y):
        new_x = []
        new_y = []
        for i in range(1, len(orig_x)-1):
            new_x.append(orig_x[i])
            new_y.append((orig_y[i-1] + orig_y[i] + orig_y[i+1]) / 3.0)
        return new_x, new_y

    def whittaker(self, orig_x, orig_y):
        new_x = []
        new_y = []
