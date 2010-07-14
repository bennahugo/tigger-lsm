from PyQt4.Qt import *
import math
import pyfits
import os.path

from Kittens.widgets import BusyIndicator
from Tigger.Widgets import FileSelector
from Tigger.Models import SkyModel,ModelClasses
from Tigger.Tools import Imaging

DEG = math.pi/180;

from astLib.astWCS import WCS

class RestoreImageDialog (QDialog):
  def __init__ (self,parent,modal=True,flags=Qt.WindowFlags()):
    QDialog.__init__(self,parent,flags);
    self.setModal(modal);
    self.setWindowTitle("Restore model into image");
    lo = QVBoxLayout(self);
    lo.setMargin(10);
    lo.setSpacing(5);
    # file selector
    self.wfile_in = FileSelector(self,label="Input FITS file:",dialog_label="Input FITS file",default_suffix="fits",file_types="FITS files (*.fits *.FITS)",file_mode=QFileDialog.ExistingFile);
    lo.addWidget(self.wfile_in);
    self.wfile_out = FileSelector(self,label="Output FITS file:",dialog_label="Output FITS file",default_suffix="fits",file_types="FITS files (*.fits *.FITS)",file_mode=QFileDialog.AnyFile);
    lo.addWidget(self.wfile_out);
    # beam size
    lo1 = QHBoxLayout();
    lo.addLayout(lo1);
    lo1.setContentsMargins(0,0,0,0);
    lo1.addWidget(QLabel("Beam FWHM, major axis:",self));
    self.wbmaj = QLineEdit(self);
    lo1.addWidget(self.wbmaj);
    lo1.addWidget(QLabel("\"     minor axis:",self));
    self.wbmin = QLineEdit(self);
    lo1.addWidget(self.wbmin);
    lo1.addWidget(QLabel("\"     P.A.:",self));
    self.wbpa = QLineEdit("0",self);
    lo1.addWidget(self.wbpa);
    lo1.addWidget(QLabel(u"\u00B0",self));
    for w in self.wbmaj,self.wbmin,self.wbpa:
      w.setValidator(QDoubleValidator(self));
    lo1 = QHBoxLayout();
    lo.addLayout(lo1);
    lo1.setContentsMargins(0,0,0,0);
    self.wfile_psf = FileSelector(self,label="Fill beam parameters by fitting PSF image:",dialog_label="PSF FITS file",default_suffix="fits",file_types="FITS files (*.fits *.FITS)",file_mode=QFileDialog.ExistingFile);
    lo1.addSpacing(32);
    lo1.addWidget(self.wfile_psf);
    # selection only
    self.wselonly = QCheckBox("restore selected model sources only",self);
    # OK/cancel buttons
    lo.addSpacing(10);
    lo2 = QHBoxLayout();
    lo.addLayout(lo2);
    lo2.setContentsMargins(0,0,0,0);
    lo2.setMargin(5);
    self.wokbtn = QPushButton("OK",self);
    self.wokbtn.setMinimumWidth(128);
    QObject.connect(self.wokbtn,SIGNAL("clicked()"),self.accept);
    self.wokbtn.setEnabled(False);
    cancelbtn = QPushButton("Cancel",self);
    cancelbtn.setMinimumWidth(128);
    QObject.connect(cancelbtn,SIGNAL("clicked()"),self.reject);
    lo2.addWidget(self.wokbtn);
    lo2.addStretch(1);
    lo2.addWidget(cancelbtn);
    self.setMinimumWidth(384);
    # signals
    QObject.connect(self.wfile_in,SIGNAL("filenameSelected"),self._fileSelected);
    QObject.connect(self.wfile_out,SIGNAL("filenameSelected"),self._fileSelected);
    QObject.connect(self.wfile_psf,SIGNAL("filenameSelected"),self._psfFileSelected);
    # internal state
    self.qerrmsg = QErrorMessage(self);

  def setModel (self,model):
    nsel = len([ src for src in model.sources if src.selected ]);
    self.wselonly.setVisible(nsel>0 and nsel<len(model.sources));
    self.model = model;
    self._fileSelected(None);

  def _fileSelected (self,filename):
    self.wokbtn.setEnabled(bool(self.wfile_in.filename() and self.wfile_out.filename()));

  def _psfFileSelected (self,filename):
    busy = BusyIndicator();
    filename = str(filename);
    self.parent().showMessage("Fitting gaussian to PSF file %s"%filename);
    try:
      bmaj,bmin,pa = [ x/DEG for x in Imaging.fitPsf(filename) ];
    except Exception,err:
      busy = None;
      self.qerrmsg.showMessage("Error fitting PSF file %s: %s"%(filename,str(err)));
      return;
    bmaj *= 3600*Imaging.FWHM;
    bmin *= 3600*Imaging.FWHM;
    self.wbmaj.setText(str(bmaj));
    self.wbmin.setText(str(bmin));
    self.wbpa.setText(str(pa));

  def accept (self):
    """Tries to restore the image, and closes the dialog if successful.""";
    # get list of sources to restore
    sources = self.model.sources;
    sel_sources = filter(lambda src:src.selected,sources);
    if len(sel_sources) > 0 and len(sel_sources) < len(sources) and self.wselonly.isChecked():
      sources = sel_sources;
    if not sources:
      self.qerrmsg.showMessage("No sources to restore.");
      return;
    busy = BusyIndicator();
    # get filenames
    infile = self.wfile_in.filename();
    outfile = self.wfile_out.filename();
    self.parent().showMessage("Restoring %d model sources to image %s, writing to %s"%(len(sources),infile,outfile));
    # read fits file
    try:
      input_hdu = pyfits.open(infile)[0];
    except Exception,err:
      busy = None;
      self.qerrmsg.showMessage("Error reading FITS file %s: %s"%(infile,str(err)));
      return;
    # get beam sizes
    try:
      bmaj = float(str(self.wbmaj.text()));
      bmin = float(str(self.wbmin.text()));
      pa = float(str(self.wbpa.text()));
    except Exception,err:
      busy = None;
      self.qerrmsg.showMessage("Invalid beam size specified");
      return;
    bmaj = bmaj/(Imaging.FWHM*3600)*DEG;
    bmin = bmin/(Imaging.FWHM*3600)*DEG;
    pa = pa*DEG;
    # restore
    Imaging.restoreSources(input_hdu,sources,bmaj,bmin,pa);
    # save fits file
    try:
      input_hdu.writeto(outfile,clobber=True);
    except Exception,err:
      busy = None;
      self.qerrmsg.showMessage("Error writing FITS file %s: %s"%(outfile,str(err)));
      return;
    self.parent().loadImage(outfile);
    busy = None;
    return QDialog.accept(self);

def restore_into_image (mainwin,model):
  dialog = getattr(mainwin,'_restore_into_image_dialog',None);
  if not dialog:
    dialog = mainwin._restore_into_image_dialog = RestoreImageDialog(mainwin);
  dialog.setModel(model);
  # show dialog
  return dialog.exec_();

from Tigger.Tools import registerTool
registerTool("Restore model into image...",restore_into_image);