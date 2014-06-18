"""
/***************************************************************************
        ValueTool           TimeTracker
                            -------------------
        begin               : 2014-06-15
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

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *

import datetime


class TimeTracker:

    def __init__(self, canvas):
        self.layer_times = dict()
        self.canvas = canvas
        # This data structure looks like:
        #{
        #   'layer_id' : datetime.datetime(2014, 2, 23),
        #}
        self.next_date = datetime.datetime(2014, 5, 7, 00, 00, 00)
        self.registry = QgsMapLayerRegistry().instance()
        self.refresh_tracker()
        QObject.connect(self.registry,
                        SIGNAL("layersAdded ( QList< QgsMapLayer * > )"),
                        self.refresh_tracker)
        QObject.connect(self.registry,
                        SIGNAL("layersRemoved ( QStringList )"),
                        self.refresh_tracker)

    def __del__(self):
        # TODO Remove any connections we made to the map canvas
        pass

    def refresh_tracker(self):
        # initialise (or re-initialise) self.layer_times
        # Empty the dictionary
        self.layer_times = {}
        # Loop through all raster layers in qgis and call
        # track_layer, populating the dictionary
        for layer_id, layer in self.registry.mapLayers().iteritems():
            if layer.type() == QgsMapLayer.RasterLayer:
                self.track_layer(layer)

    def track_layer(self, layer):
        # given a layer, determine its date and write the entry to the data
        # structure. Write dummy dates for now
        layer_id = layer.id()
        self.layer_times[layer_id] = self.next_date
        self.next_date += datetime.timedelta(days=1)

    def get_time_for_layer(self, layer):
        layer_id = layer.id()
        try:
            layer_time = self.layer_times[layer_id]
        except KeyError:
            return None
        return layer_time
