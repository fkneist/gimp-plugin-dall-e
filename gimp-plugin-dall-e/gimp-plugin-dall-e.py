#!/usr/bin/env python

from gimpfu import *
import gtk
import os
import json
import urllib2
import tempfile
import errno
import ssl

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".gimp-plugin-dall-e.json")
URL_IMAGES_EDIT = "https://api.openai.com/v1/images/edits"
URL_GET_API_KEY = "https://platform.openai.com/account/api-keys"

def delete_config_file():
    if os.path.exists(CONFIG_PATH):
        os.remove(CONFIG_PATH)
        print("File " +  CONFIG_PATH +  " deleted.")
    else:
        print("File "+  CONFIG_PATH +  " does not exist.")

def get_openai_api_key():
    try:
        if not os.path.isfile(CONFIG_PATH):
            raise IOError("Config file not found: " + CONFIG_PATH)

        with open(CONFIG_PATH) as f:
            config_data = json.load(f)

        return config_data.get("openAiApiKey", "")
    except IOError as e:
        if e.errno == errno.ENOENT:
            print('Config file not found')
        else:
            print('Other I/O error')
    return ""

def modify_config(key):

    # Create the config file if it doesn't exist
    if not os.path.isfile(CONFIG_PATH):
        with open(CONFIG_PATH, "w") as f:
            json.dump({"openAiApiKey": key}, f, indent=2)
        print("Config file created:", CONFIG_PATH)
    else:
        print("Config file already exists:", CONFIG_PATH)

def create_request(image_data, mask_data, prompt):

    open_api_key = get_openai_api_key()

    if (open_api_key == ""):
        return

    headers = {"Authorization": "Bearer " + open_api_key}
    boundary = "=== DELIMITER ==="
    part_boundary = '--' + boundary

    part_list = []
    part_list.append(part_boundary)
    part_list.append('Content-Disposition: form-data; name="n"')
    part_list.append('')
    part_list.append('1')
    part_list.append(part_boundary)
    part_list.append('Content-Disposition: form-data; name="size"')
    part_list.append('')
    part_list.append('512x512')
    part_list.append(part_boundary)
    part_list.append('Content-Disposition: form-data; name="prompt"')
    part_list.append('')
    part_list.append(prompt)
    part_list.append(part_boundary)
    part_list.append('Content-Disposition: file; name="image"; filename="image.png"')
    part_list.append('Content-Type: image/png')
    part_list.append('')
    part_list.append(image_data)
    part_list.append(part_boundary)
    part_list.append('Content-Disposition: file; name="mask"; filename="mask.png"')
    part_list.append('Content-Type: image/png')
    part_list.append('')
    part_list.append(mask_data)
    part_list.append('--' + boundary + '--')
    part_list.append('')

    body = '\r\n'.join(part_list)

    req = urllib2.Request(URL_IMAGES_EDIT, body, headers)
    req.get_method = lambda: 'POST'
    req.add_header('Content-Type', 'multipart/form-data; boundary=%s' % boundary)
    req.add_header('Content-length', len(body))
    return(req)


def open_image_in_new_layer(image, image_filename):
    new_layer = pdb.gimp_file_load_layer(image, image_filename)
    pdb.gimp_image_insert_layer(image, new_layer, None, 0)
    pdb.gimp_item_set_name(new_layer, "generated")
    pdb.gimp_image_raise_layer_to_top(image, new_layer)
    gimp.displays_flush()

def print_layers(image, prompt):
    # Get the layers of the current image
    layers = image.layers

    # Input image
    temp_image = tempfile.NamedTemporaryFile(delete=False, suffix='-image.png')
    temp_image_path = temp_image.name

    # Input mask
    temp_mask = tempfile.NamedTemporaryFile(delete=False, suffix='-mask.png')
    temp_mask_path = temp_mask.name

    # Output image
    temp_generated = tempfile.NamedTemporaryFile(delete=False, suffix='-generated.png')
    temp_generated_path = temp_generated.name

    # Print the name of each layer
    for index, layer in enumerate(layers):
        # Save the image to a file

        filename = ''

        if index == 0:
            filename = temp_mask_path
        if index == 1:
            filename = temp_image_path

        pdb.gimp_file_save(image, layer, filename, filename)

    temp_image.close()
    temp_mask.close()

    with open(temp_image_path, "rb") as f:
        image_data = f.read()

    with open(temp_mask_path, "rb") as f:
        mask_data = f.read()

    req = create_request(image_data, mask_data, prompt)

    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        https_handler = urllib2.HTTPSHandler(context=ssl_context)
        opener = urllib2.build_opener(https_handler)
        urllib2.install_opener(opener)

        response_str = urllib2.urlopen(req).read().decode()
        response_json = json.loads(response_str)

        generated_image_url = response_json['data'][0]['url']
        generated_image_response = urllib2.urlopen(generated_image_url).read()

        with open(temp_generated_path, "wb") as out:
            out.write(generated_image_response)

    except Exception as e:
        print(e)

    temp_generated.close()

    open_image_in_new_layer(image, temp_generated_path)

    os.unlink(temp_image_path)
    os.unlink(temp_mask_path)
    os.unlink(temp_generated_path)

def on_button_generate_clicked(widget, image, text_entry):
    prompt = text_entry.get_text()

    if len(prompt) == 0:
        prompt = " "

    print_layers(image, prompt)


def on_button_save_clicked(widget, ui_elements):
    key = ui_elements["ui_elements_entry"]["entry_key"].get_text()
    change_visibility(ui_elements, key)
    modify_config(key)

def on_button_reset_clicked(widget, ui_elements):
    change_visibility(ui_elements, "")
    delete_config_file()

def create_api_key_input(dialog):
    # API key input field
    entry_key = gtk.Entry()
    entry_key.set_width_chars(80) 
    entry_key.set_max_length(400)
    dialog.vbox.pack_start(entry_key, True, True, 0)

    button_save = gtk.Button("save")
    dialog.vbox.pack_start(button_save)

    return({"entry_key": entry_key, "button_save": button_save})

def create_api_key_reset(dialog):
    entry_key_masked = gtk.Entry()
    # Mask the API key
    entry_key_masked.set_can_focus(False)

    dialog.vbox.pack_start(entry_key_masked, True, True, 0)
    button_reset = gtk.Button("reset")
    dialog.vbox.pack_start(button_reset)

    return({"entry_key_masked": entry_key_masked, "button_reset": button_reset})

def create_prompt_input(dialog, image):
    # Create a text input field and add it to the dialog
    entry_prompt = gtk.Entry()
    entry_prompt.set_text("Enter your prompt")
    entry_prompt.set_width_chars(80) 
    entry_prompt.set_max_length(400)
    dialog.vbox.pack_start(entry_prompt, True, True, 0)
    entry_prompt.show()

    # Create a button and add it to the dialog
    button_generate = gtk.Button("generate")
    dialog.vbox.pack_start(button_generate)

    # Connect the onclick handler to the button's clicked signal
    # TODO: rename handler
    button_generate.connect("clicked", on_button_generate_clicked, image, entry_prompt)
    button_generate.show()
    return({"entry_prompt": entry_prompt, "button_generate": button_generate})

def create_api_key_information(dialog):
    hbox = gtk.HBox()
    label = gtk.Label("Visit the OpenAI website to get your API key:")
    link_button = gtk.LinkButton(URL_GET_API_KEY, URL_GET_API_KEY)
    label.show()
    link_button.show()
    hbox.pack_start(label, False, False, 0)
    hbox.pack_start(link_button, False, False, 0)
    hbox.show()
    dialog.vbox.pack_start(hbox, False, False, 0)


def change_visibility(ui_elements, openAIApiKey):
    # TODO: Fix visible key after reset
    
    if (openAIApiKey == ""):
        for key in ui_elements["ui_elements_entry"]:
            ui_elements["ui_elements_entry"][key].set_visible(True)

        for key in ui_elements["ui_elements_reset"]:
            ui_elements["ui_elements_reset"][key].set_visible(False)

        for key in ui_elements["ui_elements_prompt"]:
            ui_elements["ui_elements_prompt"][key].set_sensitive(False)

        ui_elements["ui_elements_entry"]["entry_key"].set_text("Enter your OpenAI API key")
    else:
        for key in ui_elements["ui_elements_entry"]:
            ui_elements["ui_elements_entry"][key].set_visible(False)

        for key in ui_elements["ui_elements_reset"]:
            ui_elements["ui_elements_reset"][key].set_visible(True)

        for key in ui_elements["ui_elements_prompt"]:
            ui_elements["ui_elements_prompt"][key].set_sensitive(True)

        ui_elements["ui_elements_reset"]["entry_key_masked"].set_text(openAIApiKey[:3] + "*" * (len(openAIApiKey) - 3))


def hello_world(image, layer):

    key = get_openai_api_key()
    
    dialog = gtk.Dialog("DALL-E", None, 0, (gtk.STOCK_OK, gtk.RESPONSE_OK))

    create_api_key_information(dialog)
    entry_key, button_save = create_api_key_input(dialog).values()
    entry_key_masked, button_reset = create_api_key_reset(dialog).values()
    entry_prompt, button_generate = create_prompt_input(dialog, image).values()

    ui_elements_entry = {"entry_key": entry_key, "button_save": button_save}
    ui_elements_reset = {"entry_key_masked": entry_key_masked, "button_reset": button_reset}
    ui_elements_prompt = {"entry_prompt": entry_prompt, "button_generate": button_generate}

    ui_elements = {
        "ui_elements_entry": ui_elements_entry,
        "ui_elements_reset": ui_elements_reset,
        "ui_elements_prompt": ui_elements_prompt,
    }

    button_save.connect("clicked", on_button_save_clicked, ui_elements)
    button_reset.connect("clicked", on_button_reset_clicked, ui_elements)

    change_visibility(ui_elements, key)

    # Show the dialog and wait for a response
    dialog.run()

    # Close the dialog
    dialog.destroy()

register(
    "gimp-plugin-dall-e",
    "DALL-E plugin",
    "Create a new image with your text string",
    "Florian Kneist",
    "Florian Kneist",
    "2023",
    "DALL-E",
    "",
    [        
        (PF_IMAGE, "image", "Input image", None),
        (PF_LAYER, "layer", "Input layer", None)
    ],
    [],
    hello_world, 
    menu="<Image>/Filters"
)

main()
