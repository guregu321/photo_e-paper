#!/usr/bin/python3
from PIL import Image, ImageOps, ImageDraw, ImageStat, ImageEnhance
import math
import os
import RPi.GPIO as GPIO
from waveshare_epd import epd2in7
import time
import yaml 
configfile = os.path.join(os.path.dirname(os.path.realpath(__file__)),'config.yaml')
infofile = os.path.join(os.path.dirname(os.path.realpath(__file__)),'info.jpg')
photo_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'images')
photo_list = os.listdir(photo_dir)

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

    # Reshape photo
    if photo_image.width / photo_image.height <= 1.5: # If photo height is larger than the screen
        # Resize
        height = round(photo_image.height * 264 / photo_image.width)
        photo_image = photo_image.resize((264, height), Image.LANCZOS)
        # Crop
        if height > 176:
            upper, lower = (height+176)/2, (height-176)/2
        else:
            upper, lower = 176, 0
        photo_image = photo_image.crop((0, lower, 264, upper))
    else: # If photo width is larger than the screen
        # Resize
        width = round(photo_image.width * 176 / photo_image.height)
        photo_image = photo_image.resize((width, 176), Image.LANCZOS)
        # Crop
        if width > 264:
            upper, lower = (width+264)/2, (width-264)/2
        else:
            upper, lower = 264, 0
        photo_image = photo_image.crop((lower, 0, upper, 176))

    # Detect average brightness
    r,g,b = ImageStat.Stat(photo_image).mean
    brightness = math.sqrt(0.241*(r**2) + 0.691*(g**2) + 0.068*(b**2))

    # Adjust brightness
    factor = 2 - brightness/100
    enhancer = ImageEnhance.Brightness(photo_image)  
    photo_image = enhancer.enhance(factor)
    
    # Make photo black/white
    photo_image = photo_image.convert("RGBA")

    # Configure the photo to display
    """
    180度にした時の分岐
    """
    if config['display']['orientation'] == 0 or config['display']['orientation'] == 180 :
        # Clear with white
        image = Image.new('L', (epd.width, epd.height), 255)
        # Display photo
        image.paste(photo_image, (0,0))
        if config['display']['orientation'] == 180 :
            image=image.rotate(180, expand=True)
    if config['display']['orientation'] == 90 or config['display']['orientation'] == 270 :
        # Clear with white
        image = Image.new('L', (epd.height, epd.width), 255)
        # Display photo
        image.paste(photo_image, (0,0))
        if config['display']['orientation'] == 270 :
            image=image.rotate(180, expand=True)
        # This is a hack to deal with the mirroring that goes on in 4Gray Horizontal
        image = ImageOps.mirror(image)

    # If the display is inverted, invert the image usinng ImageOps        
    if config['display']['inverted'] == True:
        image = ImageOps.invert(image)

    # Display the image on the screen
    print("Displaying {}".format(config['ticker']['image_list'][0]))
    epd.display_4Gray(epd.getbuffer_4Gray(image))

def display_info(epd, config):
    photo_image = Image.open(infofile)
    # Clear with white
    image = Image.new('L', (epd.height, epd.width), 255)
    # Display photo
    image.paste(photo_image, (0,0))
    if config['display']['orientation'] == 270 :
        image=image.rotate(180, expand=True)
    # This is a hack to deal with the mirroring that goes on in 4Gray Horizontal
    image = ImageOps.mirror(image)
    print("Displaying info")
    epd.display_4Gray(epd.getbuffer_4Gray(image))

def main():    
    initial_screen = False 
    info_status = False

    # Initialise the display (once before loop)
    epd = epd2in7.EPD()  
    epd.Init_4Gray()

    # Initialize the keys
    key1, key2, key3, key4 = 5, 6, 13, 19
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(key1, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(key2, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(key3, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(key4, GPIO.IN, pull_up_down=GPIO.PUD_UP) 

    # Get the configuration from config.yaml
    with open(configfile) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    config['display']['orientation'] = int(config['display']['orientation'])
    config['ticker']['image_list'] = photo_list

    # Set time
    last_time = time.time()
       
    try:
        while True:
            # Detect button press
            if all([GPIO.input(key1), GPIO.input(key2), GPIO.input(key3), GPIO.input(key4)]) == False:
                if GPIO.input(key1) == False:  # Show previous photo
                    config['ticker']['image_list'] = config['ticker']['image_list'][-1:] + config['ticker']['image_list'][:-1]
                    update_image(epd, config)  
                    info_status = False 
                    last_time=time.time()             
                elif GPIO.input(key2) == False:  # Show next photo
                    config['ticker']['image_list'] = config['ticker']['image_list'][1:] + config['ticker']['image_list'][:1]
                    update_image(epd, config)
                    info_status = False
                    last_time=time.time()
                elif GPIO.input(key3) == False:  # Rotate 90 degrees
                    config['display']['orientation'] = (config['display']['orientation']+90) % 360
                    update_image(epd, config)
                    info_status = False
                    last_time=time.time()
                
                if GPIO.input(key4) == False: # Display info
                    if info_status == True:
                        update_image(epd, config)
                        info_status = False
                    else:
                        display_info(epd, config)
                        info_status = True
                    last_time=time.time()

            # Cycle photos    
            if (time.time() - last_time > float(config['ticker']['updatefrequency'])) or (initial_screen == False):
                # Make first photo the last in the list
                if (config['display']['cycle'] == True) and (initial_screen == True):
                    config['ticker']['image_list'] = config['ticker']['image_list'][1:] + config['ticker']['image_list'][:1]
                
                # Update image
                update_image(epd, config)
                
                # Update time keeper
                last_time=time.time()
                time.sleep(0.2)

                # Update initialization status
                initial_screen = True
                info_status = False

    except KeyboardInterrupt:    
        print("ctrl + c: exiting")
        epd2in7.epdconfig.module_exit()
        GPIO.cleanup()
        exit()

if __name__ == '__main__':
    main()