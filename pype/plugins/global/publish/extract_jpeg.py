import os
import pyblish.api
import subprocess
from pype.vendor import clique


class ExtractJpegEXR(pyblish.api.InstancePlugin):
    """Resolve any dependency issies

    This plug-in resolves any paths which, if not updated might break
    the published file.

    The order of families is important, when working with lookdev you want to
    first publish the texture, update the texture paths in the nodes and then
    publish the shading network. Same goes for file dependent assets.
    """

    label = "Extract Jpeg EXR"
    order = pyblish.api.ExtractorOrder
    families = ["imagesequence", "render", "write", "source"]
    host = ["shell"]
    exclude_families = ["clip"]

    def process(self, instance):
        if [ef for ef in self.exclude_families
                for f in instance.data["families"]
                if f in ef]:
            self.log.info('ignoring: {}'.format(instance))
            return
        start = instance.data.get("startFrame")
        stagingdir = os.path.normpath(instance.data.get("stagingDir"))

        collected_frames = os.listdir(stagingdir)
        collections, remainder = clique.assemble(collected_frames)

        input_file = (
            collections[0].format('{head}{padding}{tail}') % start
        )
        full_input_path = os.path.join(stagingdir, input_file)
        self.log.info("input {}".format(full_input_path))

        filename = collections[0].format('{head}')
        if not filename.endswith('.'):
            filename += "."
        jpegFile = filename + "jpg"
        full_output_path = os.path.join(stagingdir, jpegFile)

        self.log.info("output {}".format(full_output_path))

        config_data = instance.context.data['output_repre_config']

        proj_name = os.environ.get('AVALON_PROJECT', '__default__')
        profile = config_data.get(proj_name, config_data['__default__'])

        jpeg_items = []
        jpeg_items.append("ffmpeg")
        # override file if already exists
        jpeg_items.append("-y")
        # use same input args like with mov
        jpeg_items.extend(profile.get('input', []))
        # input file
        jpeg_items.append("-i {}".format(full_input_path))
        # output file
        jpeg_items.append(full_output_path)

        subprocess_jpeg = " ".join(jpeg_items)
        sub_proc = subprocess.Popen(subprocess_jpeg)
        sub_proc.wait()

        if "files" not in instance.data:
            instance.data["files"] = list()
        instance.data["files"].append(jpegFile)
