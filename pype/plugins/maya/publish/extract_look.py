import os
import json
import tempfile
import contextlib
import subprocess
from collections import OrderedDict

from maya import cmds

import pyblish.api
import avalon.maya
from avalon import io

import pype.api
import pype.maya.lib as lib

# Modes for transfer
COPY = 1
HARDLINK = 2


def source_hash(filepath, *args):
    """Generate simple identifier for a source file.
    This is used to identify whether a source file has previously been
    processe into the pipeline, e.g. a texture.
    The hash is based on source filepath, modification time and file size.
    This is only used to identify whether a specific source file was already
    published before from the same location with the same modification date.
    We opt to do it this way as opposed to Avalanch C4 hash as this is much
    faster and predictable enough for all our production use cases.
    Args:
        filepath (str): The source file path.
    You can specify additional arguments in the function
    to allow for specific 'processing' values to be included.
    """
    # We replace dots with comma because . cannot be a key in a pymongo dict.
    file_name = os.path.basename(filepath)
    time = str(os.path.getmtime(filepath))
    size = str(os.path.getsize(filepath))
    return "|".join([
        file_name,
        time,
        size
    ] + list(args)).replace(".", ",")


def find_paths_by_hash(texture_hash):
    # Find the texture hash key in the dictionary and all paths that
    # originate from it.
    key = "data.sourceHashes.{0}".format(texture_hash)
    return io.distinct(key, {"type": "version"})


def maketx(source, destination, *args):
    """Make .tx using maketx with some default settings.
    The settings are based on default as used in Arnold's
    txManager in the scene.
    This function requires the `maketx` executable to be
    on the `PATH`.
    Args:
        source (str): Path to source file.
        destination (str): Writing destination path.
    """

    cmd = [
        "maketx",
        "-v", # verbose
        "-u", # update mode
        # unpremultiply before conversion (recommended when alpha present)
        "--unpremult",
        # use oiio-optimized settings for tile-size, planarconfig, metadata
        "--oiio"
    ]
    cmd.extend(args)
    cmd.extend([
           "-o", destination,
           source
    ])

    CREATE_NO_WINDOW = 0x08000000
    try:
        out = subprocess.check_output(
            cmd,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW
        )
    except subprocess.CalledProcessError as exc:
        print exc
        print out
        import traceback
        traceback.print_exc()
        raise

    return out


@contextlib.contextmanager
def no_workspace_dir():
    """Force maya to a fake temporary workspace directory.

    Note: This is not maya.cmds.workspace 'rootDirectory' but the 'directory'

    This helps to avoid Maya automatically remapping image paths to files
    relative to the currently set directory.

    """

    # Store current workspace
    original = cmds.workspace(query=True, directory=True)

    # Set a fake workspace
    fake_workspace_dir = tempfile.mkdtemp()
    cmds.workspace(directory=fake_workspace_dir)

    try:
        yield
    finally:
        try:
            cmds.workspace(directory=original)
        except RuntimeError:
            # If the original workspace directory didn't exist either
            # ignore the fact that it fails to reset it to the old path
            pass

        # Remove the temporary directory
        os.rmdir(fake_workspace_dir)


class ExtractLook(pype.api.Extractor):
    """Extract Look (Maya Ascii + JSON)

    Only extracts the sets (shadingEngines and alike) alongside a .json file
    that stores it relationships for the sets and "attribute" data for the
    instance members.

    """

    label = "Extract Look (Maya ASCII + JSON)"
    hosts = ["maya"]
    families = ["look"]
    order = pyblish.api.ExtractorOrder + 0.2

    def process(self, instance):

        # Define extract output file path
        dir_path = self.staging_dir(instance)
        maya_fname = "{0}.ma".format(instance.name)
        json_fname = "{0}.json".format(instance.name)

        # Make texture dump folder
        maya_path = os.path.join(dir_path, maya_fname)
        json_path = os.path.join(dir_path, json_fname)

        self.log.info("Performing extraction..")

        # Remove all members of the sets so they are not included in the
        # exported file by accident
        self.log.info("Extract sets (Maya ASCII) ...")
        lookdata = instance.data["lookData"]
        relationships = lookdata["relationships"]
        sets = relationships.keys()

        # Extract the textures to transfer, possibly convert with maketx and
        # remap the node paths to the destination path. Note that a source
        # might be included more than once amongst the resources as they could
        # be the input file to multiple nodes.
        resources = instance.data["resources"]
        do_maketx = instance.data.get("maketx", False)

        # Collect all unique files used in the resources
        files = set()
        for resource in resources:
            files.update(os.path.normpath(f) for f in resource["files"])

        # Process the resource files
        transfers = list()
        hardlinks = list()
        hashes = dict()
        for filepath in files:
            source, mode, hash = self._process_texture(
                filepath, do_maketx, staging=dir_path
            )
            destination = self.resource_destination(
                instance, source, do_maketx
            )
            if mode == COPY:
                transfers.append((source, destination))
            elif mode == HARDLINK:
                hardlinks.append((source, destination))

            # Store the hashes from hash to destination to include in the
            # database
            hashes[hash] = destination

        # Remap the resources to the destination path (change node attributes)
        destinations = dict()
        remap = OrderedDict()  # needs to be ordered, see color space values
        for resource in resources:
            source = os.path.normpath(resource["source"])
            if source not in destinations:
                # Cache destination as source resource might be included
                # multiple times
                destinations[source] = self.resource_destination(
                    instance, source, do_maketx
                )

            # Remap file node filename to destination
            attr = resource['attribute']
            remap[attr] = destinations[source]

            # Preserve color space values (force value after filepath change)
            # This will also trigger in the same order at end of context to
            # ensure after context it's still the original value.
            color_space_attr = resource['node'] + ".colorSpace"
            remap[color_space_attr] = cmds.getAttr(color_space_attr)

        self.log.info("Finished remapping destinations ...")

        # Extract in correct render layer
        layer = instance.data.get("renderlayer", "defaultRenderLayer")
        with lib.renderlayer(layer):
            # TODO: Ensure membership edits don't become renderlayer overrides
            with lib.empty_sets(sets, force=True):
                # To avoid Maya trying to automatically remap the file
                # textures relative to the `workspace -directory` we force
                # it to a fake temporary workspace. This fixes textures
                # getting incorrectly remapped. (LKD-17, PLN-101)
                with no_workspace_dir():
                    with lib.attribute_values(remap):
                        with avalon.maya.maintained_selection():
                            cmds.select(sets, noExpand=True)
                            cmds.file(
                                maya_path,
                                force=True,
                                typ="mayaAscii",
                                exportSelected=True,
                                preserveReferences=False,
                                channels=True,
                                constraints=True,
                                expressions=True,
                                constructionHistory=True
                            )

        # Write the JSON data
        self.log.info("Extract json..")
        data = {"attributes": lookdata["attributes"],
                "relationships": relationships}

        with open(json_path, "w") as f:
            json.dump(data, f)

        if "files" not in instance.data:
            instance.data["files"] = list()
        if "hardlinks" not in instance.data:
            instance.data["hardlinks"] = list()
        if "transfers" not in instance.data:
            instance.data["transfers"] = list()

        instance.data["files"].append(maya_fname)
        instance.data["files"].append(json_fname)

        # Set up the resources transfers/links for the integrator
        instance.data["transfers"].extend(transfers)
        instance.data["hardlinks"].extend(hardlinks)

        # Source hash for the textures
        instance.data["sourceHashes"] = hashes

        self.log.info("Extracted instance '%s' to: %s" % (
            instance.name, maya_path)
        )

    def resource_destination(self, instance, filepath, do_maketx):

        # Compute destination location
        basename, ext = os.path.splitext(os.path.basename(filepath))

        # If maketx then the texture will always end with .tx
        if do_maketx:
            ext = ".tx"

        return os.path.join(
            instance.data["assumedDestination"],
            "resources",
            basename + ext
        )

    def _process_texture(self, filepath, do_maketx, staging):
        """Process a single texture file on disk for publishing.
        This will:
            1. Check whether it's already published, if so it will do hardlink
            2. If not published and maketx is enabled, generate a new .tx file.
            3. Compute the destination path for the source file.
        Args:
            filepath (str): The source file path to process.
            do_maketx (bool): Whether to produce a .tx file
        Returns:
        """

        fname, ext = os.path.splitext(os.path.basename(filepath))

        args = []
        if do_maketx:
            args.append("maketx")
        texture_hash = source_hash(filepath, *args)

        # If source has been published before with the same settings,
        # then don't reprocess but hardlink from the original
        existing = find_paths_by_hash(texture_hash)
        if existing:
            self.log.info("Found hash in database, preparing hardlink..")
            source = next((p for p in existing if os.path.exists(p)), None)
            if filepath:
                return source, HARDLINK, texture_hash
            else:
                self.log.warning(
                    "Paths not found on disk, "
                    "skipping hardlink: %s" % (existing,)
                )

        if do_maketx and ext != ".tx":
            # Produce .tx file in staging if source file is not .tx
            converted = os.path.join(
                staging,
                "resources",
                fname + ".tx"
            )

            # Ensure folder exists
            if not os.path.exists(os.path.dirname(converted)):
                os.makedirs(os.path.dirname(converted))

            self.log.info("Generating .tx file for %s .." % filepath)
            maketx(filepath, converted,
                   # Include `source-hash` as string metadata
                   "-sattrib", "sourceHash", texture_hash)

            return converted, COPY, texture_hash

        return filepath, COPY, texture_hash
