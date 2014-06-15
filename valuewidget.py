"""
/***************************************************************************
         Value Tool       - A QGIS plugin to get values at the mouse pointer
                             -------------------
    begin                : 2008-08-26
    copyright            : (C) 2008 by G. Picard
    email                : 
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""

import logging
# change the level back to logging.WARNING(the default) before releasing
logging.basicConfig(level=logging.DEBUG)

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *

import fnmatch  # Import filtering for Layernames
import datetime  # for dealing with Multi-temporal data
from distutils.version import StrictVersion
import numpy as np
import time

from ui_valuewidgetbase import Ui_ValueWidgetBase as Ui_Widget

has_qwt = True
try:
    from PyQt4.Qwt5 import QwtPlot, QwtPlotCurve, QwtScaleDiv, QwtSymbol
except:
    has_qwt = False

#test if matplotlib >= 1.0
has_mpl = True
try:
    import matplotlib
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    import matplotlib.dates as dates
    from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg
except:
    has_mpl = StrictVersion(matplotlib.__version__) > StrictVersion('1.0.0')
#if has_mpl:
#    if int(matplotlib.__version__[0]) < 1:
#        has_mpl = False

# TODO: Get better debugging
debug = 0

has_pyqtgraph = True
try:
    import pyqtgraph as pg
except:
    has_pyqtgraph = StrictVersion(pyqtgraph.__version__) > StrictVersion(
        '0.9.7')


class DateAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        strns = []
        rng = max(values)-min(values)
        #if rng < 120:
        #    return pg.AxisItem.tickStrings(self, values, scale, spacing)
        if rng < 3600*24:
            string = '%H:%M:%S'
            label1 = '%b %d -'
            label2 = ' %b %d, %Y'
        elif rng >= 3600*24 and rng < 3600*24*30:
            string = '%d'
            label1 = '%b - '
            label2 = '%b, %Y'
        elif rng >= 3600*24*30 and rng < 3600*24*30*24:
            string = '%b %y'
            label1 = '%Y -'
            label2 = ' %Y'
        elif rng >=3600*24*30*24:
            string = '%Y'
            label1 = ''
            label2 = ''
        for x in values:
            try:
                strns.append(time.strftime(string, time.localtime(x)))
            except ValueError:  ## Windows can't handle dates before 1970
                strns.append('')
        try:
            label = time.strftime(label1, time.localtime(min(values)))+time.strftime(label2, time.localtime(max(values)))
        except ValueError:
            label = ''
        #self.setLabel(text=label)
        return strns

class CustomViewBox(pg.ViewBox):
    def __init__(self, *args, **kwds):
        pg.ViewBox.__init__(self, *args, **kwds)
        self.setMouseMode(self.RectMode)

    ## reimplement right-click to zoom out
    def mouseClickEvent(self, ev):
        if ev.button() == QtCore.Qt.RightButton:
            self.autoRange()

    def mouseDragEvent(self, ev):
        if ev.button() == QtCore.Qt.RightButton:
            ev.ignore()
        else:
            pg.ViewBox.mouseDragEvent(self, ev)


class ValueWidget(QWidget, Ui_Widget):

    def __init__(self, iface):
        self.hasqwt = has_qwt
        self.hasmpl = has_mpl
        self.haspqg = has_pyqtgraph
        self.layerMap = dict()
        self.statsChecked = False
        self.ymin = 0
        self.ymax = 250
        self.isActive = False
        self.mt_enabled = False

        # Statistics (>=1.9)
        self.statsSampleSize = 2500000
        self.stats = {}  # stats per layer

        self.layersSelected = []
        self.layerBands = dict()

        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        self.legend = self.iface.legendInterface()
        self.logger = logging.getLogger('.'.join((__name__,
                                        self.__class__.__name__)))
        QWidget.__init__(self)
        self.setupUi(self)
        self.tabWidget.setEnabled(False)
        self.plotOnMove.setChecked(QSettings().value(
            'plugins/valuetool/mouseClick', False, type=bool))

        # self.setupUi_plot()
        # don't setup plot until Plot tab is clicked - workaround for bug #7450
        # qgis will still crash in some cases, but at least the tool can be
        # used in Table mode
        self.qwtPlot = None
        self.mplPlot = None
        self.mplLine = None

        QObject.connect(self.plotLibSelector,
                        SIGNAL("currentIndexChanged ( int )"),
                        self.changePlot)
        QObject.connect(self.tabWidget,
                        SIGNAL("currentChanged ( int )"),
                        self.tabWidgetChanged)
        QObject.connect(self.layerSelection,
                        SIGNAL("currentIndexChanged ( int )"),
                        self.updateLayers)
        QObject.connect(self.bandSelection,
                        SIGNAL("currentIndexChanged ( int )"),
                        self.updateLayers)
        QObject.connect(self.selectionTable,
                        SIGNAL("cellChanged ( int , int )"),
                        self.layerSelected)
        QObject.connect(self.enableMTAnalysesCheckBox,
                        SIGNAL("toggled ( bool )"),
                        self.on_mt_analysis_toggled)
        QObject.connect(self.selectionStringLineEdit,
                        SIGNAL("textChanged(QString)"),
                        self.updateLayers)

        self.setupUi_plot()

    def setupUi_plot(self):

        need_library_message = QtGui.QLabel("Need Qwt >= 5.0 or "
                                            "matplotlib >= 1.0 or "
                                            "PyQtGraph > 0.9.8 !")
        # plot
        self.plotLibSelector.setVisible(False)
        self.enableStatistics.setVisible(False)
        # stats by default because estimated are fast
        self.enableStatistics.setChecked(True)

        plot_count = 0

        # Page 2 - qwt
        if self.hasqwt:
            self.plotLibSelector.addItem('Qwt')
            plot_count += 1
            self.qwtPlot = QwtPlot(self.stackedWidget)
            self.qwtPlot.setAutoFillBackground(False)
            self.qwtPlot.setObjectName("qwtPlot")
            self.curve = QwtPlotCurve()
            self.curve.setSymbol(
                QwtSymbol(QwtSymbol.Ellipse,
                          QBrush(Qt.white),
                          QPen(Qt.red, 2),
                          QSize(9, 9)))
            self.curve.attach(self.qwtPlot)
        else:
            self.qwtPlot = need_library_message

        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding,
                                       QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.qwtPlot.sizePolicy().hasHeightForWidth())
        self.qwtPlot.setSizePolicy(sizePolicy)
        self.qwtPlot.updateGeometry()
        self.stackedWidget.addWidget(self.qwtPlot)

        #Page 3 - matplotlib
        self.mplLine = None  # make sure to invalidate when layers change
        if self.hasmpl:
            self.plotLibSelector.addItem('matplotlib')
            plot_count += 1
            # mpl stuff
            # should make figure light gray
            self.mplBackground = None
            # http://www.scipy.org/Cookbook/Matplotlib/Animations
            self.mplFig = plt.Figure(facecolor='w', edgecolor='w')
            self.mplFig.subplots_adjust(left=0.1,
                                        right=0.975,
                                        bottom=0.13,
                                        top=0.95)
            self.mpl_subplot = self.mplFig.add_subplot(111)
            self.mpl_subplot.tick_params(axis='both',
                                         which='major',
                                         labelsize=12)
            self.mpl_subplot.tick_params(axis='both',
                                         which='minor',
                                         labelsize=10)
            # qt stuff
            self.pltCanvas = FigureCanvasQTAgg(self.mplFig)
            self.pltCanvas.setParent(self.stackedWidget)
            self.pltCanvas.setAutoFillBackground(False)
            self.pltCanvas.setObjectName("mplPlot")
            self.mplPlot = self.pltCanvas
        else:
            self.mplPlot = need_library_message

        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding,
                                       QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.mplPlot.sizePolicy().hasHeightForWidth())
        self.mplPlot.setSizePolicy(sizePolicy)
        self.mplPlot.updateGeometry()
        self.stackedWidget.addWidget(self.mplPlot)

        if self.haspqg:
            self.plotLibSelector.addItem('PyQtGraph')
            plot_count += 1
            # Setup PyQtGraph stuff
            self.pqg_axis = DateAxis(orientation='bottom')
            vb = CustomViewBox()
            pg.setConfigOption('background', 'w')
            pg.setConfigOption('foreground', 'k')
            self.pqg_plot_widget = pg.PlotWidget(parent=self.stackedWidget,
                                                 viewBox=vb, axisItems={
                    'bottom': self.pqg_axis}, enableMenu=False, title="Kick my "
                                                                   "balls")
        else:
            self.pqg_plot_widget = need_library_message

        self.pqg_plot_widget.setSizePolicy(sizePolicy)
        self.pqg_plot_widget.updateGeometry()
        self.stackedWidget.addWidget(self.pqg_plot_widget)

        if plot_count > 1:
            self.plotLibSelector.setEnabled(True)
            self.plotLibSelector.setVisible(True)
            self.plotLibSelector.setCurrentIndex(0)
        else:
            if self.hasqwt:
                self.plotLibSelector.setCurrentIndex(0)
            elif self.hasmpl:
                self.plotLibSelector.setCurrentIndex(1)
            else:
                self.plotLibSelector.setCurrentIndex(2)

    def keyPressEvent(self, e):
        if (e.modifiers() == Qt.ControlModifier or e.modifiers() == Qt.MetaModifier) and e.key() == Qt.Key_C:
            items = ''
            for rec in range(self.valueTable.rowCount()):
                items += '"' + self.valueTable.item(rec, 0).text() + '",' + self.valueTable.item(rec, 1).text() + "\n"
            if not items == '':
                clipboard = QApplication.clipboard()
                clipboard.setText(items)
        else:
            QWidget.keyPressEvent(self, e)

    def changePlot(self):
        # TODO Add the magic for pyqtgraph here?
        if self.plotLibSelector.currentText() == 'Qwt':
            self.stackedWidget.setCurrentIndex(0)
        elif self.plotLibSelector.currentText() == 'matplotlib':
            self.stackedWidget.setCurrentIndex(1)
        elif self.plotLibSelector.currentText() == 'PyQtGraph':
            self.stackedWidget.setCurrentIndex(2)

    def changeActive(self, active, gui=True):
        self.isActive = active

        if active:
            self.toggleValueTool.setCheckState(Qt.Checked)
            QObject.connect(self.canvas,
                            SIGNAL("layersChanged ()"),
                            self.invalidatePlot)
            if not self.plotOnMove.isChecked():
                QObject.connect(self.canvas,
                                SIGNAL("xyCoordinates(const QgsPoint &)"),
                                self.printValue)
        else:
            self.toggleValueTool.setCheckState(Qt.Unchecked)
            QObject.disconnect(self.canvas,
                               SIGNAL("layersChanged ()"),
                               self.invalidatePlot)
            QObject.disconnect(self.canvas,
                               SIGNAL("xyCoordinates(const QgsPoint &)"),
                               self.printValue)

        if gui:
            self.tabWidget.setEnabled(active)
            if active:
                self.labelStatus.setText(self.tr("Value tool is enabled!"))
                if self.tabWidget.currentIndex() == 2:
                    self.updateLayers()
            else:
                self.labelStatus.setText(self.tr(""))
                #use this to clear plot when deactivated
                #self.values=[]
                #self.showValues()

    def activeRasterLayers(self, index=None):
        layers = []
        allLayers = []

        if not index:
            index = self.layerSelection.currentIndex()
        if index == 0:
            allLayers = self.canvas.layers()
        elif index == 1 or index == 3:
            allLayers = self.legend.layers()
        elif index == 2:
            for layer in self.legend.layers():
                if layer.id() in self.layersSelected:
                    allLayers.append(layer)

        for layer in allLayers:

            if index == 3:
                # Check if the layer name matches our filter and skip it if it
                # doesn't
                if not self.name_matches_filter(layer.name()):
                    continue

            if layer is not None and layer.isValid() and \
                    layer.type() == QgsMapLayer.RasterLayer and \
                    layer.dataProvider() and \
                    (layer.dataProvider().capabilities() & QgsRasterDataProvider.IdentifyValue):
                layers.append(layer)

        return layers

    def activeBandsForRaster(self, layer):
        activeBands = []

        if self.bandSelection.currentIndex() == 1 and layer.renderer():
            activeBands = layer.renderer().usesBands()
        elif self.bandSelection.currentIndex() == 2:
            if layer.bandCount() == 1:
                activeBands = [1]
            else:
                activeBands = self.layerBands[layer.id()] if (layer.id() in self.layerBands) else []
        else:
            activeBands = range(1, layer.bandCount()+1)

        return activeBands

    def printValue(self, position):

        if debug > 0:
            print(position)

        if not position:
            return
        if self.tabWidget.currentIndex() == 2:
            return

        if debug > 0:
            print("%d active rasters, %d canvas layers" % (len(
                self.activeRasterLayers()), self.canvas.layerCount()))
        layers = self.activeRasterLayers()

        if len(layers) == 0:
            if self.canvas.layerCount() > 0:
                self.labelStatus.setText(self.tr("No valid layers to display "
                                                 "- change layers in Options"))
            else:
                self.labelStatus.setText(self.tr("No valid layers to display"))
            self.values = []
            self.showValues()
            return

        self.labelStatus.setText(self.tr('Coordinate:') + ' (%f, %f)' % (
            position.x(), position.y()))

        need_extremum = (self.tabWidget.currentIndex() == 1)  # if plot is shown
        # count the number of required rows and remember the raster layers
        nrow = 0
        rasterlayers = []
        layersWOStatistics = []

        for layer in layers:
            nrow += layer.bandCount()
            rasterlayers.append(layer)

            # check statistics for each band
            if need_extremum:
                for i in range(1, layer.bandCount()+1):
                    has_stats = self.get_statistics(layer, i) is not None
                    if not layer.id() in self.layerMap and not has_stats \
                            and not layer in layersWOStatistics:
                        layersWOStatistics.append(layer)

        if layersWOStatistics and not self.statsChecked:
            self.calculateStatistics(layersWOStatistics)

        irow = 0
        self.values = []
        self.ymin = 1e38
        self.ymax = -1e38

        mapCanvasSrs = self.iface.mapCanvas().mapRenderer().destinationCrs()

        # TODO - calculate the min/max values only once,
        # instead of every time!!!
        # And keep them in a dict() with key=layer.id()

        counter = 0
        for layer in rasterlayers:
            layer_name = unicode(layer.name())
            layer_srs = layer.crs()

            pos = position

            # if given no position, get dummy values
            if position is None:
                pos = QgsPoint(0, 0)
            # transform points if needed
            elif not mapCanvasSrs == layer_srs and \
                    self.iface.mapCanvas().hasCrsTransformEnabled():
                srsTransform = QgsCoordinateTransform(mapCanvasSrs, layer_srs)
                try:
                    pos = srsTransform.transform(position)
                except QgsCsException, err:
                    # ignore transformation errors
                    continue

            if True:  # for QGIS >= 1.9
                if not layer.dataProvider():
                    continue
                ident = None

                if position is not None:
                    canvas = self.iface.mapCanvas()

                    # first test if point is within map layer extent
                    # maintain same behaviour as in 1.8 and print out of extent
                    if not layer.dataProvider().extent().contains(pos):
                        ident = dict()
                        for iband in range(1, layer.bandCount()+1):
                            ident[iband] = str(self.tr('out of extent'))
                    # we can only use context if layer is not projected
                    elif canvas.hasCrsTransformEnabled() and layer.dataProvider().crs() != canvas.mapRenderer().destinationCrs():
                        ident = layer.dataProvider().identify(pos, QgsRaster.IdentifyFormatValue ).results()
                    else:
                        extent = canvas.extent()
                        width = round(extent.width() / canvas.mapUnitsPerPixel())
                        height = round(extent.height() / canvas.mapUnitsPerPixel())
                        extent = canvas.mapRenderer().mapToLayerCoordinates(layer, extent)
                        ident = layer.dataProvider().identify(pos, QgsRaster.IdentifyFormatValue, canvas.extent(), width, height).results()
                    if not len(ident) > 0:
                        continue

                # if given no position, set values to 0
                if position is None and ident is not None and ident.iterkeys() is not None:
                    for key in ident.iterkeys():
                        ident[key] = layer.dataProvider().noDataValue(key)

                # bands displayed depends on cbxBands (all / active / selected)
                activeBands = self.activeBandsForRaster(layer)

                for iband in activeBands:  # loop over the active bands
                    layer_name_with_band = layer_name
                    if ident is not None and len(ident) > 1:
                        layer_name_with_band += ' ' + layer.bandName(iband)

                    if not ident or not ident.has_key(iband):  #should not happen
                        bandvalue = "?"
                    else:
                        bandvalue = ident[iband]
                        if bandvalue is None:
                            bandvalue = "no data"

                    tup = (layer_name_with_band, counter+1, str(bandvalue))
                    self.values.append(tup)

                    if need_extremum:
                        # estimated statistics
                        stats = self.get_statistics(layer, iband)
                        if stats:
                            self.ymin = min(self.ymin, stats.minimumValue)
                            self.ymax = max(self.ymax, stats.maximumValue)
                    counter += 1

        if len(self.values) == 0:
            self.labelStatus.setText(self.tr("No valid bands to display"))

        self.showValues()

    def showValues(self):
        if self.tabWidget.currentIndex() == 1:
            #TODO don't plot if there is no data to plot...
            self.plot()
        else:
            self.printInTable()

    def calculateStatistics(self, layersWOStatistics):

        self.invalidatePlot(False)

        self.statsChecked = True

        layernames = []
        for layer in layersWOStatistics:
            if not layer.id() in self.layerMap:
                layernames.append(layer.name())

        if len(layernames) != 0:
            if not self.enableStatistics.isChecked():
                for layer in layersWOStatistics:
                    self.layerMap[layer.id()] = True
                return
        else:
            print('ERROR, no layers to get stats for')

        save_state = self.isActive
        self.changeActive(False, False)  # deactivate

        # calculate statistics
        for layer in layersWOStatistics:
            if not layer.id() in self.layerMap:
                self.layerMap[layer.id()] = True
                for i in range(1, layer.bandCount()+1):
                    self.get_statistics(layer, i, True)

        if save_state:
            self.changeActive(True, False)  # activate if necessary

    # get cached statistics for layer and band or None if not calculated
    def get_statistics(self, layer, bandNo, force=False):
        if self.stats.has_key(layer):
            if self.stats[layer].has_key(bandNo):
                return self.stats[layer][bandNo]
        else:
            self.stats[layer] = {}

        if force or \
                layer.dataProvider().hasStatistics(bandNo,
                                                   QgsRasterBandStats.Min | QgsRasterBandStats.Min,
                                                   QgsRectangle(),
                                                   self.statsSampleSize):
            self.stats[layer][bandNo] = \
                layer.dataProvider().bandStatistics(bandNo,
                                                    QgsRasterBandStats.Min | QgsRasterBandStats.Min,
                                                    QgsRectangle(),
                                                    self.statsSampleSize)
            return self.stats[layer][bandNo]
        return None

    def printInTable(self):
        # set table widget row count
        self.valueTable.setRowCount(len(self.values))
        irow = 0
        for layername, xval, value in self.values:

            # limit number of decimal places if requested
            if self.cbxDigits.isChecked():
                try:
                    value = str("{0:."+str(self.spinDigits.value())+"f}").format(float(value))
                except ValueError:
                    pass

            if self.valueTable.item(irow, 0) is None:
                # create the item
                self.valueTable.setItem(irow, 0, QTableWidgetItem())
                self.valueTable.setItem(irow, 1, QTableWidgetItem())

            self.valueTable.item(irow, 0).setText(layername)
            self.valueTable.item(irow, 1).setText(value)
            irow += 1

    def plot(self):
        data_values = []
        if self.hasqwt or self.hasmpl or self.haspqg:
            for layername, xval, value in self.values:
                try:
                    data_values.append(float(value))
                except:
                    data_values.append(0)

        ymin = self.ymin
        ymax = self.ymax

        if self.leYMin.text() != '' and self.leYMax.text() != '':
            ymin = float(self.leYMin.text())
            ymax = float(self.leYMax.text())

        if self.hasqwt and (self.plotLibSelector.currentText() == 'Qwt'):
            self.qwtPlot.setAxisMaxMinor(QwtPlot.xBottom, 0)
            #self.qwtPlot.setAxisMaxMajor(QwtPlot.xBottom,0)
            self.qwtPlot.setAxisScale(QwtPlot.xBottom, 1, len(self.values))
            #self.qwtPlot.setAxisScale(QwtPlot.yLeft,self.ymin,self.ymax)
            self.qwtPlot.setAxisScale(QwtPlot.yLeft, ymin, ymax)
            self.curve.setData(range(1, len(data_values)+1), data_values)
            self.qwtPlot.replot()
            self.qwtPlot.setVisible(len(data_values) > 0)

        elif self.haspqg and (self.plotLibSelector.currentText() ==
                                  'PyQtGraph'):
            self.pqg_plot_widget.clear()  # clean canvas on call
            # draw with pyqtgraph test
            if self.mt_enabled:
                pg.setConfigOption('background', 'w')
                pg.setConfigOption('foreground', 'k')
                #for i in range(3):
                 #   plotWidget.plot(x, y[i], pen=(i, 3))  ## setting pen=(i,
                    # 3) automaticaly creates three different-colored pens
                dates = np.arange(8) * (3600*24*356)
                self.pqg_plot_widget.plot(x=dates, y=[1, 6, 2, 4, 3, 5, 6, 8],
                                          symbol='o')
                #self.pqg_plot_widget.show()
            else:
                xValues = []
                for i in range(len(data_values)):
                    xValues.append(1+i)
                self.pqg_plot_widget.plot(xValues, data_values)

        elif self.hasmpl and (self.plotLibSelector.currentText() ==
                              'matplotlib'):
            self.mpl_subplot.clear()

            # If Multi-temporal Analysis enabled set xAxis away from Standard
            # 1 to values to dates.
            if self.mt_enabled:
                # temporal Date creation
                xValues = []
                for i in range(len(data_values)):
                    xValues.append(datetime.datetime(2014, 1, 1+i))

                # Plotcode from here
                self.mpl_subplot.plot_date(xValues,
                            data_values,
                            'b-',
                            xdate=True,
                            ydate=False,
                            marker='o',
                            color='k',
                            mfc='b',
                            mec='b')

                # hours = dates.HourLocator()
                # days = dates.DayLocator()
                # years = dates.YearLocator()   # every year
                # months = dates.MonthLocator()  # every month
                # major_formatter = dates.DateFormatter('%b')
                # minor_formatter = dates.DateFormatter('%j')
                # self.mpl_subplot.xaxis.set_major_locator(months)
                # self.mpl_subplot.xaxis.set_major_formatter(major_formatter)
                #
                # self.mpl_subplot.xaxis.set_minor_locator(days)
                # self.mpl_subplot.xaxis.set_minor_formatter(minor_formatter)
                #
                # labels = self.mpl_subplot.get_xticklabels()
                # for label in labels:
                #     label.set_rotation(45)
                #     label.set_color('orange')

                self.mplFig.autofmt_xdate()

                self.mpl_subplot.set_xlim((min(xValues)-datetime.timedelta(
                    hours=6), max(xValues)+datetime.timedelta(hours=6)))

                self.mpl_subplot.set_ylim((ymin, ymax))
            else:
                xmin = 1
                xmax = xmin + len(data_values)
                xValues = range(xmin, xmax)
                self.mpl_subplot.plot(xValues,
                            data_values,
                            marker='o',
                            color='k',
                            mfc='b',
                            mec='b')

                self.mpl_subplot.xaxis.set_major_locator(ticker.MaxNLocator(
                    integer=True))
                self.mpl_subplot.yaxis.set_minor_locator(ticker.AutoMinorLocator())
                self.mpl_subplot.set_xlim((min(xValues)-0.25, max(xValues)+0.25))
                self.mpl_subplot.set_ylim((ymin, ymax))

            self.mplFig.canvas.draw()

    def invalidatePlot(self, replot=True):
        if self.tabWidget.currentIndex() == 2:
            self.updateLayers()
        if not self.isActive:
            return
        self.statsChecked = False
        if self.mplLine is not None:
            del self.mplLine
            self.mplLine = None
        #update empty plot
        if replot and self.tabWidget.currentIndex() == 1:
            #self.values=[]
            self.printValue(None)

    def resizeEvent(self, event):
        self.invalidatePlot()

    def tabWidgetChanged(self):
        #if self.tabWidget.currentIndex() == 1 and (self.hasmpl or self.haspqg):
        #    self.setupUi_plot()
        if self.tabWidget.currentIndex() == 2:
            self.updateLayers()

    def on_mt_analysis_toggled(self, new_state):
        if new_state == 1:
            self.mt_enabled = True
            self.priorityLabel.setEnabled(True)
            self.extractionPriorityListWidget.setEnabled(True)
            self.patternLabel.setEnabled(True)
            self.patternLineEdit.setEnabled(True)
            self.writeMetaDataCheckBox.setEnabled(True)
            self.labelStatus.setText(self.tr("Multi-temporal analysis "
                                             "enabled!"))
        else:
            self.mt_enabled = False
            self.priorityLabel.setEnabled(False)
            self.extractionPriorityListWidget.setEnabled(False)
            self.patternLabel.setEnabled(False)
            self.patternLineEdit.setEnabled(False)
            self.writeMetaDataCheckBox.setEnabled(False)
            self.labelStatus.setText(self.tr(""))

    def name_matches_filter(self, name):
        selection_string = self.selectionStringLineEdit.text()
        return fnmatch.fnmatchcase(name, selection_string)

    # update active layers in table
    def updateLayers(self):
        if self.tabWidget.currentIndex() != 2:
            return

        if self.layerSelection.currentIndex() == 3:
            self.selectionStringLineEdit.setEnabled(True)
        else:
            self.selectionStringLineEdit.setEnabled(False)

        if self.layerSelection.currentIndex() == 0:
            layers = self.activeRasterLayers(0)
        elif self.layerSelection.currentIndex() == 3:
            layers = self.activeRasterLayers(3)
        else:
            layers = self.activeRasterLayers(1)

        self.selectionTable.blockSignals(True)
        self.selectionTable.clearContents()
        self.selectionTable.setRowCount(len(layers))
        self.selectionTable.horizontalHeader().resizeSection(0, 20)
        self.selectionTable.horizontalHeader().resizeSection(2, 20)

        j = 0
        for layer in layers:
            item = QTableWidgetItem()
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if self.layerSelection.currentIndex() != 2:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                item.setCheckState(Qt.Checked)
            else:
                if layer.id() in self.layersSelected:
                    item.setCheckState(Qt.Checked)
                else:
                    item.setCheckState(Qt.Unchecked)
            self.selectionTable.setItem(j, 0, item)
            item = QTableWidgetItem(layer.name())
            item.setData(Qt.UserRole, layer.id())
            self.selectionTable.setItem(j, 1, item)
            activeBands = self.activeBandsForRaster(layer)
            button = QToolButton()
            button.setText("#")  # TODO add edit? icon
            button.setPopupMode(QToolButton.InstantPopup)
            group = QActionGroup(button)
            group.setExclusive(False)
            QObject.connect(group,
                            SIGNAL("triggered(QAction*)"),
                            self.bandSelected)
            if self.bandSelection.currentIndex() == 2 and layer.bandCount() > 1:
                menu = QMenu()
                menu.installEventFilter(self)

                for iband in range(1, layer.bandCount()+1):
                    action = QAction(str(layer.bandName(iband)), group)
                    action.setData([layer.id(), iband, j, False])
                    action.setCheckable(True)
                    action.setChecked(iband in activeBands)
                    menu.addAction(action)
                if layer.bandCount() > 1:
                    action = QAction(str(self.tr("All")), group)
                    action.setData([layer.id(), -1, j, True])
                    action.setCheckable(False)
                    menu.addAction(action)
                    action = QAction(str(self.tr("None")), group)
                    action.setData([layer.id(), -1, j, False])
                    action.setCheckable(False)
                    menu.addAction(action)

                button.setMenu(menu)
            else:
                button.setEnabled(False)
            self.selectionTable.setCellWidget(j, 2, button)
            item = QTableWidgetItem(str(activeBands))
            item.setToolTip(str(activeBands))
            self.selectionTable.setItem(j, 3, item)
            j = j + 1

        self.selectionTable.blockSignals(False)

    # slot for when active layer selection has changed
    def layerSelected(self, row, column):
        if column != 0:
            return

        self.layersSelected = []
        for i in range(0, self.selectionTable.rowCount()):
            item = self.selectionTable.item(i, 0)
            layerID = self.selectionTable.item(i, 1).data(Qt.UserRole)
            if item and item.checkState() == Qt.Checked:
                self.layersSelected.append(layerID)
            elif layerID in self.layersSelected:
                self.layersSelected.remove(layerID)

    # slot for when active band selection has changed
    def bandSelected(self, action):
        layerID = action.data()[0]
        layerBand = action.data()[1]
        j = action.data()[2]
        toggleAll = action.data()[3]
        activeBands = self.layerBands[layerID] if (layerID in
                                                   self.layerBands) else []

        # special actions All/None
        if layerBand == -1:
            for layer in self.legend.layers():
                if layer.id() == layerID:
                    if toggleAll:
                        activeBands = range(1, layer.bandCount()+1)
                    else:
                        activeBands = []
                    # toggle all band# actions
                    group = action.parent()
                    if group and not isinstance(group, QtGui.QActionGroup):
                        group = None
                    if group:
                        group.blockSignals(True)
                        for a in group.actions():
                            if a.isCheckable():
                                a.setChecked(toggleAll)
                        group.blockSignals(False)

        # any Band# action
        else:
            if action.isChecked():
                activeBands.append(layerBand)
            else:
                if layerBand in activeBands:
                    activeBands.remove(layerBand)
            activeBands.sort()

        self.layerBands[layerID] = activeBands

        # update UI
        item = QTableWidgetItem(str(activeBands))
        item.setToolTip(str(activeBands))
        self.selectionTable.setItem(j, 3, item)

    # event filter for band selection menu, do not close after toggling each
    # band
    def eventFilter(self, obj, event):
        if event.type() in [QtCore.QEvent.MouseButtonRelease]:
            if isinstance(obj, QtGui.QMenu):
                if obj.activeAction():
                    if not obj.activeAction().menu():  # if the selected
                    # action does not have a submenu eat the event,
                    # but trigger the function
                        obj.activeAction().trigger()
                        return True
        return super(ValueWidget, self).eventFilter(obj, event)

    def shouldPrintValues(self):
        return self.isVisible() and not self.visibleRegion().isEmpty() and \
               self.isActive and self.tabWidget.currentIndex() != 2

    def toolMoved(self, position):
        if self.shouldPrintValues() and not self.plotOnMove.isChecked():
            self.printValue(self.canvas.getCoordinateTransform().toMapCoordinates(position))

    def toolPressed(self, position):
        if self.shouldPrintValues() and self.plotOnMove.isChecked():
            self.printValue(self.canvas.getCoordinateTransform().toMapCoordinates(position))