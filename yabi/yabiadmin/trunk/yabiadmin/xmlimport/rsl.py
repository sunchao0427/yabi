"""
Import a ToolRslInfo from an .rsl file into the DB.

Invoke import_rsl(filename) to import one file at a time.
To import all files from a directory look at the functions defined
at the module level. 
Django's ORM is used to save the entities to the DB, so the easiest
way to run the import is from a Django shell (ie. ./manage.py shell or
./manage.py shell_plus if you have Django extensions installed).
"""
import os, sys
from xml.dom.minidom import parse
from yabiadmin.admin.models import Tool, ToolRslInfo

def import_rsl(filename):
    tool = find_associated_tool(filename)
    assert tool, "Couldn't find tool for filename %s. Can't proceed!" % filename
    rsl_infos = ToolRslInfo.objects.filter(tool=tool)
    assert not rsl_infos, "A tool rsl info for tool (%d: %s) already exists." \
                           % (tool.id, tool.name) + "Can't proceed!"

    doc = parse(filename)
    root_element = doc.firstChild
    assert root_element.nodeName == "job", 'The root element should be called "job"'

    rsl_info = ToolRslInfo(tool=tool)
    populate_rsl_info_fields(rsl_info, root_element)
    args = extract_argument_orders(root_element)
    modules = extract_extension_modules(root_element)

    rsl_info.save()
    save_argument_orders(rsl_info, args)
    save_extension_modules(rsl_info, modules)

def find_associated_tool(filename):
    tool_name = os.path.splitext(os.path.basename(filename))[0]
    tools = Tool.objects.filter(name=tool_name)
    if tools:
        return tools[0]

def get_value(parent_element, element_name):
    element = parent_element.getElementsByTagName(element_name)[0]
    return element.firstChild.data

def populate_rsl_info_fields(rsl_info, root_elem):
    rsl_info.executable = get_value(root_elem, 'executable')
    rsl_info.count = get_value(root_elem, 'count')
    rsl_info.queue = get_value(root_elem, 'queue')
    rsl_info.max_wall_time = get_value(root_elem, 'maxWallTime')
    rsl_info.max_memory = get_value(root_elem, 'maxMemory')
    rsl_info.job_type = get_value(root_elem, 'jobType')

def extract_argument_orders(root_elem):
    args_only = lambda c: c.nodeName in ('argument', 'argumentPlaceholder')
    arg_name = lambda a: a.nodeName == 'argumentPlaceholder' and 'ALL' or a.firstChild.data
    arguments = [arg_name(arg) for arg in root_elem.childNodes if args_only(arg)]
    return arguments or ['ALL']

def extract_extension_modules(root_elem):
    modules = []
    for extension_elem in root_elem.getElementsByTagName("extensions"):
        for module in extension_elem.getElementsByTagName("module"):
            modules.append(module.firstChild.data)
    return modules

def save_argument_orders(rsl_info, args):
    for i, arg in enumerate(args):
        rsl_info.toolrslargumentorder_set.create(name=arg,rank=i+1)

def save_extension_modules(rsl_info, modules):
    for module in modules:
        rsl_info.toolrslextensionmodule_set.create(name=module)

if __name__ == '__main__':
    import_rsl(sys.argv[1])

