#!/usr/bin/python3
from PIL import Image, ImageOps, ImageFont, ImageDraw
import os
import sys
import logging
import RPi.GPIO as GPIO
from waveshare_epd import epd2in7
import time
os.environ['TZ'] = 'Asia/Tokyo'
time.tzset()
import requests
import urllib, json
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import yaml 
import socket
import textwrap
configfile = os.path.join(os.path.dirname(os.path.realpath(__file__)),'config.yaml')
photo_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'images')
photo_list = os.listdir(photo_dir)

def _place_text(img, text, x_offset=0, y_offset=0, fontsize=40, fill=0):
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans.ttf', fontsize)
    img_width, img_height = img.size
    text_width, _ = font.getsize(text)
    text_height = fontsize
    draw_x = (img_width - text_width)//2 + x_offset
    draw_y = (img_height - text_height)//2 + y_offset
    draw.text((draw_x, draw_y), text, font=font, fill=fill)

# Line break text
def writewrappedlines(img, text, fontsize=16, y_text=20, height=15, width=25):
    lines = textwrap.wrap(text, width)
    numoflines=0
    for line in lines:
        _place_text(img, line, 0, y_text, fontsize)
        y_text += height
        numoflines += 1
    return img

# Create error screen
def beanaproblem(epd, message):
    # Clear with white
    image = Image.new('L', (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(image)

    # Paste the bean
    thebean = Image.open(os.path.join(picdir, 'thebean.bmp'))
    image.paste(thebean, (60,45))
    writewrappedlines(image, "Problem:"+message)
    image = ImageOps.mirror(image)
    epd.display_4Gray(epd.getbuffer_4Gray(image))
    thebean.close()
    # Reload last good config.yaml
    with open(configfile) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    return image

def update_image(epd, config):
    # Load image
    photo_path = os.path.join(photo_dir, config['ticker']['image_list'][0])
    photo_image = Image.open(photo_path)

    # Fix orientation: PIL changes the orientation of vertical images
    exif = photo_image._getexif()
    convert_image = {
        1: lambda img: img,
        2: lambda img: img.transpose(Image.FLIP_LEFT_RIGHT),
        3: lambda img: img.transpose(Image.ROTATE_180),
        4: lambda img: img.transpose(Image.FLIP_TOP_BOTTOM),
        5: lambda img: img.transpose(Image.FLIP_LEFT_RIGHT).transpose(Pillow.ROTATE_90),
        6: lambda img: img.transpose(Image.ROTATE_270),
        7: lambda img: img.transpose(Image.FLIP_LEFT_RIGHT).transpose(Pillow.ROTATE_270),
        8: lambda img: img.transpose(Image.ROTATE_90),}
    orientation = exif.get(0x112, 1)
    photo_image = convert_image[orientation](photo_image)

    """
    画像の高さが足りない場合の処理を入れる
    """
    # Resize
    height = round(photo_image.height * 264 / photo_image.width)
    photo_image = photo_image.resize((264, height), Image.LANCZOS)

    # Crop
    if height > 176:
        upper, lower = (height+176)/2, (height-176)/2
    else:
        upper, lower = 176, 0
    photo_image = photo_image.crop((0, lower, 264, upper))

    # Make the photo black/white
    photo_image = photo_image.convert("RGBA")

    # Configure the photo to display
    if config['display']['orientation'] == 0 or config['display']['orientation'] == 180 :
        # Clear with white
        image = Image.new('L', (epd.width, epd.height), 255)
        draw = ImageDraw.Draw(image)
        # Display photo
        image.paste(photo_image, (0,0))
        if config['display']['orientation'] == 180 :
            image=image.rotate(180, expand=True)
    if config['display']['orientation'] == 90 or config['display']['orientation'] == 270 :
        # Clear with white
        image = Image.new('L', (epd.height, epd.width), 255)
        draw = ImageDraw.Draw(image) 
        #Display photo
        image.paste(photo_image, (0,0))
        if config['display']['orientation'] == 270 :
            image=image.rotate(180, expand=True)
        # This is a hack to deal with the mirroring that goes on in 4Gray Horizontal
        image = ImageOps.mirror(image)

    # If the display is inverted, invert the image usinng ImageOps        
    if config['display']['inverted'] == True:
        image = ImageOps.invert(image)

    # Return the photo
    return image 


def main():    
    logging.basicConfig(level=logging.DEBUG)
    initial_screen=False 

    # Initialise the display (once before loop)
    epd = epd2in7.EPD()  
    epd.Init_4Gray()
    logging.info("epd2in7 Picture Frame")

    try:
        # Get the configuration from config.yaml
        with open(configfile) as f:
            config = yaml.load(f, Loader=yaml.FullLoader)
        config['display']['orientation']=int(config['display']['orientation'])
        config['ticker']['image_list'] = photo_list
        
        # Set time
        last_time = time.time()

        # Get the buttons for 2.7in EPD set up
        key1 = 5
        key2 = 6
        key3 = 13
        key4 = 19
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(key1, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(key2, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(key3, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(key4, GPIO.IN, pull_up_down=GPIO.PUD_UP) 
        
        while True:
            # Detect button press
            key1state = GPIO.input(key1)
            key2state = GPIO.input(key2)
            key3state = GPIO.input(key3)
            key4state = GPIO.input(key4)
            if key1state == False:
                logging.info('Cycle currencies')
                crypto_list = currencycycle(config['ticker']['currency'])
                config['ticker']['currency']=",".join(crypto_list)
                last_time=fullupdate(epd, config, last_time)
            if key2state == False:
                logging.info('Rotate - 90')
                config['display']['orientation'] = (config['display']['orientation']+90) % 360
                last_time=fullupdate(epd,last_time)
            if key3state == False:
                logging.info('Invert Display')
                config['display']['inverted'] = not config['display']['inverted']
                last_time=fullupdate(epd,config,last_time)
            if key4state == False:
                logging.info('Cycle fiat')
                fiat_list = currencycycle(config['ticker']['fiatcurrency'])
                config['ticker']['fiatcurrency']=",".join(fiat_list)
                last_time=fullupdate(epd,config,last_time)

            # Cycle photos    
            if (time.time() - last_time > float(config['ticker']['updatefrequency'])) or (initial_screen == False):
                # Update image
                image = update_image(epd, config)
                epd.display_4Gray(epd.getbuffer_4Gray(image))
                
                # Update time keeper
                last_time=time.time()
                time.sleep(0.2)

                # Update initialization status
                initial_screen = True
                
                # Make first photo the last in the list
                if config['display']['cycle'] == True:
                    config['ticker']['image_list'] = photo_list[1:] + photo_list[:1]

    except IOError as e:
        logging.info(e)
        image = beanaproblem(epd, str(e))
        epd.display_4Gray(epd.getbuffer_4Gray(image)) 
    except KeyboardInterrupt:    
        logging.info("ctrl + c:")
        epd2in7.epdconfig.module_exit()
        GPIO.cleanup()
        exit()

if __name__ == '__main__':
    main()
