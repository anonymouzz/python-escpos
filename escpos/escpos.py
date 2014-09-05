#!/usr/bin/python
'''
@author: Manuel F Martinez <manpaz@bashlinux.com>
@organization: Bashlinux
@copyright: Copyright (c) 2012 Bashlinux
@license: GPL
'''

try:
    import Image
except ImportError:
    from PIL import Image

import qrcode
import barcode
from barcode.writer import ImageWriter
import time

from constants import *
from exceptions import *


class EscposIO(object):

    ''' ESC/POS Printer IO object'''
    def __init__(self, printer, autocut=True, autoclose=True):
        self.printer = printer
        self.params = {}
        self.autocut = autocut
        self.autoclose = autoclose

    def set(self, **kwargs):
        """
        :type bold:         bool
        :param bold:        set bold font
        :type underline:    [None, 1, 2]
        :param underline:   underline text
        :type size:         ['normal', '2w', '2h' or '2x']
        :param size:        Text size
        :type font:         ['a', 'b', 'c']
        :param font:        Font type
        :type align:        ['left', 'center', 'right']
        :param align:       Text position
        :type inverted:     boolean
        :param inverted:    White on black text
        :type color:        [1, 2]
        :param color:       Text color
        :rtype:             NoneType
        :returns:            None
        """

        self.params.update(kwargs)

    def raw(self, msg):
        """ Print any of the commands above, or clear text """
        self.printer._raw(msg)

    def reset(self):
        self.raw(RESET)

    def close(self):
        self.printer.close()

    def __enter__(self, **kwargs):
        return self

    def __exit__(self, type, value, traceback):
        if not (type is not None and issubclass(type, Exception)):
            if self.autocut:
                self.printer.cut()
        if self.autoclose:
            self.close()


class Escpos(object):
    """ ESC/POS Printer object """
    device = None
    _codepage = None
    stored_args = {}
    text_style = None

    def _check_image_size(self, size):
        """ Check and fix the size of the image to 32 bits """
        if size % 32 == 0:
            return (0, 0)
        else:
            image_border = 32 - (size % 32)
            if (image_border % 2) == 0:
                return (image_border / 2, image_border / 2)
            else:
                return (image_border / 2, (image_border / 2) + 1)

    def _print_image(self, line, size):
        """ Print formatted image """
        i = 0
        cont = 0
        buffer = ""

        # align center
        if text_align:
            text_align = self.text_style.get('align', None)
        self.device.raw(TEXT_STYLE['align']['center'])

        self.device.raw(S_RASTER_N)
        buffer = "%02X%02X%02X%02X" % (((size[0] / size[1]) / 8), 0, size[1], 0)
        self.device.raw(buffer.decode('hex'))
        buffer = ""

        while i < len(line):
            hex_string = int(line[i:i + 8], 2)
            buffer += "%02X" % hex_string
            i += 8
            cont += 1
            if cont % 4 == 0:
                self.device.raw(buffer.decode("hex"))
                buffer = ""
                cont = 0
        # restore align
        if text_align:
            self.device.raw(TEXT_STYLE['align'][text_align])

    def _convert_image(self, im):
        """ Parse image and prepare it to a printable format """
        pixels = []
        pix_line = ""
        im_left = ""
        im_right = ""
        switch = 0
        img_size = [0, 0]

        if im.size[0] > 512:
            print("WARNING: Image is wider than 512 and could be truncated at print time ")
        if im.size[1] > 255:
            raise ImageSizeError()

        im_border = self._check_image_size(im.size[0])
        for i in range(im_border[0]):
            im_left += "0"
        for i in range(im_border[1]):
            im_right += "0"

        for y in range(im.size[1]):
            img_size[1] += 1
            pix_line += im_left
            img_size[0] += im_border[0]
            for x in range(im.size[0]):
                img_size[0] += 1
                RGB = im.getpixel((x, y))
                im_color = (RGB[0] + RGB[1] + RGB[2])
                im_pattern = "1X0"
                pattern_len = len(im_pattern)
                switch = (switch - 1) * (-1)
                for x in range(pattern_len):
                    if im_color <= (255 * 3 / pattern_len * (x + 1)):
                        if im_pattern[x] == "X":
                            pix_line += "%d" % switch
                        else:
                            pix_line += im_pattern[x]
                        break
                    elif im_color > (255 * 3 / pattern_len * pattern_len) and im_color <= (255 * 3):
                        pix_line += im_pattern[-1]
                        break
            pix_line += im_right
            img_size[0] += im_border[1]

        return pix_line, img_size

    def image(self, path_img):
        """ Open image file """
        im_open = Image.open(path_img)
        im = im_open.convert("RGB")
        # Convert the RGB image in printable image
        self._convert_image(im)

    def qr(self, text, *args, **kwargs):
        """ Print QR Code for the provided string """
        qr_args = dict(
            version=4,
            box_size=4,
            border=1,
            error_correction=qrcode.ERROR_CORRECT_M
        )

        qr_args.update(kwargs)

        if qr_args['box_size'] > MAX_QR_BOX_SIZE:
            qr_args['box_size'] = MAX_QR_BOX_SIZE

        qr_code = qrcode.QRCode(**qr_args)

        qr_code.add_data(text)
        qr_code.make(fit=True)
        qr_img = qr_code.make_image()
        im = qr_img._img.convert("RGB")
        # Convert the RGB image in printable image
        pix_line, img_size = self._convert_image(im)
        # and print it
        self._print_image(pix_line, img_size)

    def barcode(self, code, bc, width, height, pos, font):
        if self.device.printer.barcode:
            self._font_barcode(code, bc, width, height, pos, font)
        else:
            self._graph_barcode(code, bc, width, height, pos, font)

    def _graph_barcode(self, code, bc, width, height, pos, font):
        ''' Print Barcode for the provided string '''
        img_writer = ImageWriter()
        dpi = self.device.printer.dpi
        if width or height:
            if width >= 1 or width <= 255:
                if width > 90 and width < 180:
                    dpi = 180
                if width > 180:
                    dpi = 300
        img_writer.dpi = dpi
        bcode = barcode.get(bc.lower(), code, writer=img_writer)
        img = bcode.render().convert('RGB')
        # convert image for printable format
        pix_line, img_size = self._convert_image(img)
        # and print it
        self._print_image(pix_line, img_size)

    def _font_barcode(self, code, bc, width, height, pos, font):
        """ Print Barcode """
        # Align Bar Code()
        self.device.raw(TEXT_STYLE['align']['center'])
        #
        # Position
        #
        if pos.upper() == "OFF":
            self.device.raw(BARCODE_TXT_OFF)
        elif pos.upper() == "BOTH":
            self.device.raw(BARCODE_TXT_BTH)
        elif pos.upper() == "ABOVE":
            self.device.raw(BARCODE_TXT_ABV)
        else:  # DEFAULT POSITION: BELOW
            self.device.raw(BARCODE_TXT_BLW)
        #
        # Height
        #
        if height >= 2 or height <= 6:
            self.device.raw(BARCODE_HEIGHT)
        else:
            raise BarcodeSizeError()
        #
        # Width
        #
        if width >= 1 or width <= 255:
            self.device.raw(BARCODE_WIDTH)
        else:
            raise BarcodeSizeError()
        #
        # Font
        #
        #if font.upper() == "B":
        #    self.device.raw(BARCODE_FONT_B)
        #else:  # DEFAULT FONT: A
        #    self.device.raw(BARCODE_FONT_A)
                #
        # Type
        #
        if bc.upper() == "UPC-A":
            self.device.raw(BARCODE_UPC_A)
        elif bc.upper() == "UPC-E":
            self.device.raw(BARCODE_UPC_E)
        elif bc.upper() == "EAN13":
            self.device.raw(BARCODE_EAN13)
        elif bc.upper() == "EAN8":
            self.device.raw(BARCODE_EAN8)
        elif bc.upper() == "CODE39":
            self.device.raw(BARCODE_CODE39)
        elif bc.upper() == "ITF":
            self.device.raw(BARCODE_ITF)
        elif bc.upper() == "NW7":
            self.device.raw(BARCODE_NW7)
        else:
            raise BarcodeTypeError()
        #
        # Print Code
        #
        if code:
            self.device.raw(code)
            self.device.raw(NUL)
            self.device.raw(CTL_LF)
        else:
            raise exception.BarcodeCodeError()
        self.device.raw(TEXT_STYLE['align'][self.text_style['align']])

    def writelines(self, text, **kwargs):
        if isinstance(text, unicode) or isinstance(text, str):
            lines = text.split('\n')
        elif isinstance(text, list) or isinstance(text, tuple):
            lines = text
        else:
            lines = ["{0}".format(text), ]

        for line in lines:
            if isinstance(text, unicode):
                self.device.raw(u"{0}\n".format(line).encode(self._codepage))
            else:
                self.device.raw("{0}\n".format(line))

    def text(self, text):
        """ Print alpha-numeric text """
        self.writelines(text, **self.stored_args)

    def set(self, codepage=None, **kwargs):
        """
        :type bold:         bool
        :param bold:        set bold font
        :type underline:    [None, 1, 2]
        :param underline:   underline text
        :type size:         ['normal', '2w', '2h' or '2x']
        :param size:        Text size
        :type font:         ['a', 'b', 'c']
        :param font:        Font type
        :type align:        ['left', 'center', 'right']
        :param align:       Text position
        :type inverted:     boolean
        :param inverted:    White on black text
        :type color:        [1, 2]
        :param color:       Text color
        :rtype:             NoneType
        :returns:            None
        """

        for key in kwargs.iterkeys():
            if not key in TEXT_STYLE:
                raise KeyError('Parameter {0} is wrong.'.format(key))

        for key, value in TEXT_STYLE.iteritems():
            if key in kwargs:
                cur = kwargs[key]
                if isinstance(cur, str) or isinstance(cur, unicode):
                    cur = cur.lower()

                if cur in value:
                    self.device.raw(value[cur])
                else:
                    raise AttributeError(
                        'Attribute {0} is wrong.'.format(cur)
                    )

        self.text_style = kwargs

        if 'align' not in self.text_style:
            if not self.text_style:
                self.text_style = dict()
            self.text_style['align'] = 'left'

        # Codepage
        self._codepage = codepage
        if codepage:
            self.device.raw(PAGE_CP_SET_COMMAND + PAGE_CP_CODE[codepage])

    def cut(self, mode='', postfix=POSTFIX):
        """ Cut paper """
        # Fix the size between last line and cut
        # TODO: handle this with a line feed
        self.device.raw(postfix)
        if mode.upper() == "PART":
            self.device.raw(PAPER_PART_CUT)
        else:  # DEFAULT MODE: FULL CUT
            self.device.raw(PAPER_FULL_CUT)
        self.device.raw(FF)

    def cashdraw(self, pin):
        """ Send pulse to kick the cash drawer """
        if pin == 2:
            self.device.raw(CD_KICK_2)
        elif pin == 5:
            self.device.raw(CD_KICK_5)
        else:
            raise CashDrawerError()

    def hw(self, hw):
        """ Hardware operations """
        if hw.upper() == "INIT":
            self.device.raw(HW_INIT)
        elif hw.upper() == "SELECT":
            self.device.raw(HW_SELECT)
        elif hw.upper() == "RESET":
            self.device.raw(HW_RESET)
        else:  # DEFAULT: DOES NOTHING
            pass

        self._codepage = None

    def control(self, ctl):
        """ Feed control sequences """
        if ctl.upper() == "LF":
            self.device.raw(CTL_LF)
        elif ctl.upper() == "FF":
            self.device.raw(CTL_FF)
        elif ctl.upper() == "CR":
            self.device.raw(CTL_CR)
        elif ctl.upper() == "HT":
            self.device.raw(CTL_HT)
        elif ctl.upper() == "VT":
            self.device.raw(CTL_VT)

    def close(self):
        self.device.raw(RESET)
        self.__del__()

    def __del__(self):
        """ Release device interface """
        if self.device:
            try:
                self.device.printer.__del__()
            except Exception, err:
                print err
                self.device.printer, self.device = None, None
                # Give a chance to return the interface to the system
                # The following message could appear if the application is executed
                # too fast twice or more times.
                #
                # >> could not detach kernel driver from interface 0: No data available
                # >> No interface claimed
                time.sleep(1)
