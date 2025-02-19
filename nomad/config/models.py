#
# Copyright The NOMAD Authors.
#
# This file is part of NOMAD. See https://nomad-lab.eu for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os
from enum import Enum
import logging
import inspect
from typing import TypeVar, List, Dict, Tuple, Any, Union, Optional, cast
from typing_extensions import Literal, Annotated  # type: ignore
from pydantic import BaseModel, Field, root_validator, Extra  # pylint: disable=unused-import
from pkg_resources import get_distribution, DistributionNotFound

try:
    __version__ = get_distribution('nomad-lab').version
except DistributionNotFound:
    # package is not installed
    pass


NomadSettingsBound = TypeVar('NomadSettingsBound', bound='NomadSettings')


class NomadSettings(BaseModel):
    def customize(
        self: NomadSettingsBound,
        custom_settings: Union[NomadSettingsBound, Dict[str, Any]],
    ) -> NomadSettingsBound:
        """
        Returns a new config object, created by taking a copy of the current config and
        updating it with the settings defined in `custom_settings`. The `custom_settings` can
        be a NomadSettings or a dictionary (in the latter case it must not contain any new keys
        (keys not defined in this NomadSettings). If it does, an exception will be raised.
        """

        rv = self.copy(deep=True)

        if custom_settings:
            if isinstance(custom_settings, BaseModel):
                for field_name in custom_settings.__fields__.keys():
                    try:
                        setattr(rv, field_name, getattr(custom_settings, field_name))
                    except Exception:
                        raise AssertionError(f'Invalid setting: {field_name}')
            elif isinstance(custom_settings, dict):
                for key, value in custom_settings.items():
                    if value is None:
                        continue
                    try:
                        setattr(rv, key, value)
                    except Exception:
                        raise AssertionError(f'Invalid setting: ({key}: {value})')

        return cast(NomadSettingsBound, rv)


class StrictSettings(NomadSettings, extra=Extra.ignore):
    """A warning is printed when extra fields are specified for these models."""

    @root_validator(pre=True)
    def __print_extra_field__(cls, values):  # pylint: disable=no-self-argument
        extra_fields = values.keys() - cls.__fields__.keys()

        if extra_fields:
            logger = logging.getLogger(__name__)
            logger.warning(
                f'The following unknown fields in the config are ignored: {extra_fields}'
            )

        return values


class OptionsBase(StrictSettings):
    """The most basic model for defining the availability of different
    options.
    """

    include: Optional[List[str]] = Field(
        description="""
        List of included options. If not explicitly defined, all of the options will
        be included by default.
    """
    )
    exclude: Optional[List[str]] = Field(
        description="""
        List of excluded options. Has higher precedence than include.
    """
    )

    def filter(self, value: str) -> bool:
        """Determines is a value fitting this specification."""
        included = not self.include or value in self.include or '*' in self.include
        excluded = self.exclude and (value in self.exclude or '*' in self.exclude)

        return included and not excluded


class OptionsGlob(StrictSettings):
    """Controls the availability of different options with the possibility of
    using glob/wildcard syntax.
    """

    include: Optional[List[str]] = Field(
        description="""
        List of included options. Supports glob/wildcard syntax.
    """
    )
    exclude: Optional[List[str]] = Field(
        description="""
        List of excluded options. Supports glob/wildcard syntax. Has higher precedence than include.
    """
    )


class Options(OptionsBase):
    """Common configuration class used for enabling/disabling certain
    elements and defining the configuration of each element.
    """

    options: Optional[Dict[str, Any]] = Field(
        {}, description='Contains the available options.'
    )

    def filtered_keys(self) -> List[str]:
        """Returns a list of keys that fullfill the include/exclude
        requirements.
        """
        if self.include is None or '*' in self.include:
            include = list(self.options.keys())
        else:
            include = self.include
        if self.exclude is not None and '*' in self.exclude:
            return []
        else:
            exclude = self.exclude or []
        return [key for key in include if key not in exclude]

    def filtered_values(self) -> List[Any]:
        """Returns a list of values that fullfill the include/exclude
        requirements.
        """
        return [
            self.options[key] for key in self.filtered_keys() if key in self.options
        ]

    def filtered_items(self) -> List[Tuple[str, Any]]:
        """Returns a list of key/value pairs that fullfill the include/exclude
        requirements.
        """
        return [
            (key, self.options[key])
            for key in self.filtered_keys()
            if key in self.options
        ]


class OptionsSingle(Options):
    """Represents options where one value can be selected."""

    selected: str = Field(description='Selected option.')


class OptionsMulti(Options):
    """Represents options where multiple values can be selected."""

    selected: List[str] = Field(description='Selected options.')


class Services(NomadSettings):
    """
    Contains basic configuration of the NOMAD services (app, worker, north).
    """

    api_host = Field(
        'localhost',
        description="""
        The external hostname that clients can use to reach this NOMAD installation.
    """,
    )
    api_port = Field(
        8000,
        description="""
        The port used to expose the NOMAD app and api to clients.
    """,
    )
    api_base_path = Field(
        '/fairdi/nomad/latest',
        description="""
        The base path prefix for the NOMAD app and api.
    """,
    )
    api_secret = Field(
        'defaultApiSecret',
        description="""
        A secret that is used to issue download and other tokens.
    """,
    )
    api_timeout = Field(
        600,
        description="""
        If the NOMAD app is run with gunicorn as process manager, this timeout (in s) is passed
        and worker processes will be restarted, if they do not respond in time.
    """,
    )
    https = Field(
        False,
        description="""
        Set to `True`, if external clients are using *SSL* to connect to this installation.
        Requires to setup a reverse-proxy (e.g. the one used in the docker-compose
        based installation) that handles the *SSL* encryption.
    """,
    )
    https_upload = Field(
        False,
        description="""
        Set to `True`, if upload curl commands should suggest the use of SSL for file
        uploads. This can be configured independently of `https` to suggest large file
        via regular HTTP.
    """,
    )
    admin_user_id = Field(
        '00000000-0000-0000-0000-000000000000',
        description="""
        The admin user `user_id`. All users are treated the same; there are no
        particular authorization information attached to user accounts. However, the
        API will grant the user with the given `user_id` more rights, e.g. using the
        `admin` owner setting in accessing data.
    """,
    )

    encyclopedia_base = Field(
        'https://nomad-lab.eu/prod/rae/encyclopedia/#',
        description="""
            This enables links to the given *encyclopedia* installation in the UI.
        """,
    )
    aitoolkit_enabled = Field(
        False,
        description="""
        If true, the UI will show a menu with links to the AI Toolkit notebooks on
        `nomad-lab.eu`.
    """,
    )
    optimade_enabled = Field(
        True, description="""If true, the app will serve the optimade API."""
    )
    dcat_enabled = Field(
        True, description="""If true the app will serve the DCAT API."""
    )
    h5grove_enabled = Field(
        True, description="""If true the app will serve the h5grove API."""
    )

    console_log_level = Field(
        logging.WARNING,
        description="""
        The log level that controls console logging for all NOMAD services (app, worker, north).
        The level is given in Python `logging` log level numbers.
    """,
    )

    upload_limit = Field(
        10,
        description="""
        The maximum allowed unpublished uploads per user. If a user exceeds this
        amount, the user cannot add more uploads.
    """,
    )
    force_raw_file_decoding = Field(
        False,
        description="""
        By default, text raw-files are interpreted with utf-8 encoding. If this fails,
        the actual encoding is guessed. With this setting, we force to assume iso-8859-1
        encoding, if a file is not decodable with utf-8.
    """,
    )
    max_entry_download = Field(
        50000,
        description="""
        There is an inherent limit in page-based pagination with Elasticsearch. If you
        increased this limit with your Elasticsearch, you can also adopt this setting
        accordingly, changing the maximum amount of entries that can be paginated with
        page-base pagination.

        Page-after-value-based pagination is independent and can be used without limitations.
    """,
    )
    unavailable_value = Field(
        'unavailable',
        description="""
        Value that is used in `results` section Enum fields (e.g. system type, spacegroup, etc.)
        to indicate that the value could not be determined.
    """,
    )
    app_token_max_expires_in = Field(
        30 * 24 * 60 * 60,
        description="""
        Maximum expiration time for an app token in seconds. Requests with a higher value
        will be declined.
    """,
    )
    html_resource_http_max_age = Field(
        60,
        description="""
        Used for the max_age cache-control directive on statically served html, js, css
        resources.
    """,
    )
    image_resource_http_max_age = Field(
        30 * 24 * 60 * 60,
        description="""
        Used for the max_age cache-control directive on statically served image
        resources.
    """,
    )


class Meta(NomadSettings):
    """
    Metadata about the deployment and how it is presented to clients.
    """

    version = Field(__version__, description='The NOMAD version string.')
    commit = Field(
        '',
        description="The source-code commit that this installation's NOMAD version is build from.",
    )
    deployment = Field(
        'devel', description='Human-friendly name of this nomad deployment.'
    )
    deployment_url: str = Field(description="The NOMAD deployment's url (api url).")
    label: str = Field(
        None,
        description="""
        An additional log-stash data key-value pair added to all logs. Can be used
        to differentiate deployments when analyzing logs.
    """,
    )
    service = Field(
        'unknown nomad service',
        description="""
        Name for the service that is added to all logs. Depending on how NOMAD is
        installed, services get a name (app, worker, north) automatically.
    """,
    )

    name = Field(
        'NOMAD', description='Web-site title for the NOMAD UI.', deprecated=True
    )
    homepage = Field(
        'https://nomad-lab.eu', description='Provider homepage.', deprecated=True
    )
    source_url = Field(
        'https://gitlab.mpcdf.mpg.de/nomad-lab/nomad-FAIR',
        description='URL of the NOMAD source-code repository.',
        deprecated=True,
    )

    maintainer_email = Field(
        'markus.scheidgen@physik.hu-berlin.de',
        description='Email of the NOMAD deployment maintainer.',
    )
    beta: dict = Field(
        {},
        description="""
        Additional data that describes how the deployment is labeled as a beta-version in the UI.
    """,
    )


class Oasis(NomadSettings):
    """
    Settings related to the configuration of a NOMAD Oasis deployment.
    """

    is_oasis = Field(
        False,
        description='Set to `True` to indicate that this deployment is a NOMAD Oasis.',
    )
    allowed_users: str = Field(
        None,
        description="""
        A list of usernames or user account emails. These represent a white-list of
        allowed users. With this, users will need to login right-away and only the
        listed users might use this deployment. All API requests must have authentication
        information as well.""",
    )
    uses_central_user_management = Field(
        False,
        description="""
        Set to True to use the central user-management. Typically the NOMAD backend is
        using the configured `keycloak` to access user data. With this, the backend will
        use the API of the central NOMAD (`central_nomad_deployment_url`) instead.
    """,
    )
    central_nomad_deployment_url = Field(
        'https://nomad-lab.eu/prod/v1/api',
        description="""
        The URL of the API of the NOMAD deployment that is considered the *central* NOMAD.
    """,
    )


class RabbitMQ(NomadSettings):
    """
    Configures how NOMAD is connecting to RabbitMQ.
    """

    host = Field('localhost', description='The name of the host that runs RabbitMQ.')
    user = Field('rabbitmq', description='The RabbitMQ user that is used to connect.')
    password = Field('rabbitmq', description='The password that is used to connect.')


CELERY_WORKER_ROUTING = 'worker'
CELERY_QUEUE_ROUTING = 'queue'


class Celery(NomadSettings):
    max_memory = 64e6  # 64 GB
    timeout = 1800  # 1/2 h
    acks_late = False
    routing = CELERY_QUEUE_ROUTING
    priorities = {
        'Upload.process_upload': 5,
        'Upload.delete_upload': 9,
        'Upload.publish_upload': 10,
    }


class FS(NomadSettings):
    tmp = '.volumes/fs/tmp'
    staging = '.volumes/fs/staging'
    staging_external: str = None
    public = '.volumes/fs/public'
    public_external: str = None
    north_home = '.volumes/fs/north/users'
    north_home_external: str = None
    local_tmp = '/tmp'
    prefix_size = 2
    archive_version_suffix: Union[str, List[str]] = Field(
        'v1.2',
        description="""
        This allows to add an additional segment to the names of archive files and
        thereby allows different NOMAD installations to work with the same storage
        directories and raw files, but with separate archives.

        If this is a list, the first string is used. If the file with the first
        string does not exist on read, the system will look for the file with the
        next string, etc.
    """,
    )
    working_directory = os.getcwd()
    external_working_directory: str = None


class Elastic(NomadSettings):
    host = 'localhost'
    port = 9200
    timeout = 60
    bulk_timeout = 600
    bulk_size = 1000
    entries_per_material_cap = 1000
    entries_index = 'nomad_entries_v1'
    materials_index = 'nomad_materials_v1'
    username: Optional[str]
    password: Optional[str]


class Keycloak(NomadSettings):
    server_url = 'https://nomad-lab.eu/fairdi/keycloak/auth/'
    public_server_url: str = None
    realm_name = 'fairdi_nomad_prod'
    username = 'admin'
    password = 'password'
    client_id = 'nomad_public'
    client_secret: str = None


class Mongo(NomadSettings):
    """Connection and usage settings for MongoDB."""

    host: str = Field(
        'localhost', description='The name of the host that runs mongodb.'
    )
    port: int = Field(27017, description='The port to connect with mongodb.')
    db_name: str = Field('nomad_v1', description='The used mongodb database name.')
    username: Optional[str]
    password: Optional[str]


class Logstash(NomadSettings):
    enabled = False
    host = 'localhost'
    tcp_port = '5000'
    level: int = logging.DEBUG


class Logtransfer(NomadSettings):
    """Configuration of logtransfer and statistics service.

    Note that other configurations are also used within logtransfer

    * class Logstash (Configs: enabled, host, level, tcp_port) such that logs are send to the logstash proxy
    * class Oasis (Config: central_nomad_api_url) address to which the logs are sent to
    * class FS (Config: tmp) path where collected logfiles are stored until they are transferred
    """

    # for logtransfer, see nomad/logtransfer.py
    enable_logtransfer: bool = Field(
        False,
        description='If enabled this starts process that frequently generates logs with statistics.',
    )
    submit_interval: int = Field(
        60 * 60 * 24,
        description='Time interval in seconds after which logs are transferred.',
    )
    max_bytes: int = Field(
        int(1e7),
        description='The size of the logfile in bytes at which the logs are transferred.',
    )
    backup_count: int = Field(
        10,
        description='Number of logfiles stored before oldest rotated logfile is removed.',
    )
    log_filename: str = Field(
        'collectedlogs.txt',
        description='Filename of logfile (located in ".volumes/tmp/").',
    )
    raise_unexpected_exceptions: bool = Field(
        False,
        description='Whether to keep the server alive if an unexpected exception is raised. Set to True for testing.',
    )
    # for statistics (which are submitted to logstash/logtransfer), see nomad/statistics.py
    enable_statistics: bool = Field(
        True,
        description='If enabled this starts a process that frequently generates logs with statistics.',
    )
    statistics_interval: int = Field(
        60 * 60 * 24,
        description='Time interval in seconds in which statistics are logged.',
    )


class Tests(NomadSettings):
    default_timeout = 60
    assume_auth_for_username: str = Field(
        None,
        description=(
            'Will assume that all API calls with no authentication have authentication for '
            'the user with the given username.'
        ),
    )


class Mail(NomadSettings):
    enabled = False
    with_login = False
    host = ''
    port = 8995
    user = ''
    password = ''
    from_address = 'support@nomad-lab.eu'
    cc_address: Optional[str]


class Normalize(NomadSettings):
    normalizers: Options = Field(
        Options(
            include=[
                'OptimadeNormalizer',
                'ResultsNormalizer',
                'MetainfoNormalizer',
            ],
            options=dict(
                PorosityNormalizer='nomad.normalizing.porosity.PorosityNormalizer',
                OptimadeNormalizer='nomad.normalizing.optimade.OptimadeNormalizer',
                ResultsNormalizer='nomad.normalizing.results.ResultsNormalizer',
                MetainfoNormalizer='nomad.normalizing.metainfo.MetainfoNormalizer',
            ),
        )
    )
    system_classification_with_clusters_threshold = Field(
        64,
        description="""
            The system size limit for running the dimensionality analysis. For very
            large systems the dimensionality analysis will get too expensive.
        """,
    )
    clustering_size_limit = Field(
        600,
        description="""
            The system size limit for running the system clustering. For very
            large systems the clustering will get too expensive.
        """,
    )
    symmetry_tolerance = Field(
        0.1,
        description="""
            Symmetry tolerance controls the precision used by spglib in order to
            find symmetries. The atoms are allowed to move this much from their
            symmetry positions in order for spglib to still detect symmetries.
            The unit is angstroms. The value of 0.1 is used e.g. by Materials
            Project according to
            https://pymatgen.org/pymatgen.symmetry.html#pymatgen.symmetry.analyzer.SpacegroupAnalyzer
        """,
    )
    prototype_symmetry_tolerance = Field(
        0.1,
        description="""
            The symmetry tolerance used in aflow prototype matching. Should only be
            changed before re-running the prototype detection.
        """,
    )
    max_2d_single_cell_size = Field(
        7,
        description="""
            Maximum number of atoms in the single cell of a 2D material for it to be
            considered valid.
        """,
    )
    cluster_threshold = Field(
        2.5,
        description="""
            The distance tolerance between atoms for grouping them into the same
            cluster. Used in detecting system type.
        """,
    )
    angle_rounding = Field(
        float(10.0),
        description="""
            Defines the "bin size" for rounding cell angles for the material hash in degree.
        """,
    )
    flat_dim_threshold = Field(
        0.1,
        description="""
            The threshold for a system to be considered "flat". Used e.g. when
            determining if a 2D structure is purely 2-dimensional to allow extra rigid
            transformations that are improper in 3D but proper in 2D.
        """,
    )
    k_space_precision = Field(
        150e6,
        description="""
            The threshold for point equality in k-space. Unit: 1/m.
        """,
    )
    band_structure_energy_tolerance = Field(
        8.01088e-21,
        description="""
            The energy threshold for how much a band can be on top or below the fermi
            level in order to still detect a gap. Unit: Joule.
        """,
    )
    springer_db_path = Field(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'normalizing/data/springer.msg'
        )
    )


class Resources(NomadSettings):
    enabled = False
    db_name = 'nomad_v1_resources'
    max_time_in_mongo = Field(
        60 * 60 * 24 * 365.0,
        description="""
            Maxmimum time a resource is stored in mongodb before being updated.
        """,
    )
    download_retries = Field(
        2, description='Number of retries when downloading resources.'
    )
    download_retry_delay = Field(10, description='Delay between retries in seconds')
    max_connections = Field(
        10, description='Maximum simultaneous connections used to download resources.'
    )


class Client(NomadSettings):
    user: str = None
    password: str = None
    access_token: str = None
    url = 'http://nomad-lab.eu/prod/v1/api'


class DataCite(NomadSettings):
    mds_host = 'https://mds.datacite.org'
    enabled = False
    prefix = '10.17172'
    user = '*'
    password = '*'


class GitLab(NomadSettings):
    private_token = 'not set'


class Process(NomadSettings):
    store_package_definition_in_mongo = Field(
        False,
        description='Configures whether to store the corresponding package definition in mongodb.',
    )
    add_definition_id_to_reference = Field(
        False,
        description="""
        Configures whether to attach definition id to `m_def`, note it is different from `m_def_id`.
        The `m_def_id` will be exported with the `with_def_id=True` via `m_to_dict`.
    """,
    )
    write_definition_id_to_archive = Field(
        False, description='Write `m_def_id` to the archive.'
    )
    index_materials = True
    reuse_parser = True
    metadata_file_name = 'nomad'
    metadata_file_extensions = ('json', 'yaml', 'yml')
    auxfile_cutoff = 100
    parser_matching_size = 150 * 80  # 150 lines of 80 ASCII characters per line
    max_upload_size = 32 * (1024**3)
    use_empty_parsers = False
    redirect_stdouts: bool = Field(
        False,
        description="""
        True will redirect lines to stdout (e.g. print output) that occur during
        processing (e.g. created by parsers or normalizers) as log entries.
    """,
    )
    rfc3161_skip_published = False  # skip published entries, regardless of timestamp


class Reprocess(NomadSettings):
    """
    Configures standard behaviour when reprocessing.
    Note, the settings only matter for published uploads and entries. For uploads in
    staging, we always reparse, add newfound entries, and delete unmatched entries.
    """

    rematch_published = True
    reprocess_existing_entries = True
    use_original_parser = False
    add_matched_entries_to_published = True
    delete_unmatched_published_entries = False
    index_individual_entries = False


class RFC3161Timestamp(NomadSettings):
    server = Field(
        'http://zeitstempel.dfn.de', description='The rfc3161ng timestamping host.'
    )
    cert: str = Field(
        None,
        description='Path to the optional rfc3161ng timestamping server certificate.',
    )
    hash_algorithm = Field(
        'sha256',
        description='Hash algorithm used by the rfc3161ng timestamping server.',
    )
    username: str = None
    password: str = None


class BundleExportSettings(NomadSettings):
    include_raw_files: bool = Field(
        True, description='If the raw files should be included in the export'
    )
    include_archive_files: bool = Field(
        True, description='If the parsed archive files should be included in the export'
    )
    include_datasets: bool = Field(
        True, description='If the datasets should be included in the export'
    )


class BundleExport(NomadSettings):
    """Controls behaviour related to exporting bundles."""

    default_cli_bundle_export_path: str = Field(
        './bundles',
        description='Default path used when exporting bundles using the CLI command.',
    )
    default_settings: BundleExportSettings = Field(
        BundleExportSettings(),
        description="""
            General default settings.
        """,
    )
    default_settings_cli: BundleExportSettings = Field(
        None,
        description="""
            Additional default settings, applied when exporting using the CLI. This allows
            to override some of the settings specified in the general default settings above.
        """,
    )


class BundleImportSettings(NomadSettings):
    include_raw_files: bool = Field(
        True, description='If the raw files should be included in the import'
    )
    include_archive_files: bool = Field(
        True, description='If the parsed archive files should be included in the import'
    )
    include_datasets: bool = Field(
        True, description='If the datasets should be included in the import'
    )

    include_bundle_info: bool = Field(
        True,
        description='If the bundle_info.json file should be kept (not necessary but may be nice to have.',
    )
    keep_original_timestamps: bool = Field(
        False,
        description="""
            If all timestamps (create time, publish time etc) should be imported from
            the bundle.
        """,
    )
    set_from_oasis: bool = Field(
        True,
        description='If the from_oasis flag and oasis_deployment_url should be set.',
    )

    delete_upload_on_fail: bool = Field(
        False, description='If False, it is just removed from the ES index on failure.'
    )
    delete_bundle_on_fail: bool = Field(
        True, description='Deletes the source bundle if the import fails.'
    )
    delete_bundle_on_success: bool = Field(
        True, description='Deletes the source bundle if the import succeeds.'
    )
    delete_bundle_include_parent_folder: bool = Field(
        True,
        description='When deleting the bundle, also include parent folder, if empty.',
    )

    trigger_processing: bool = Field(
        False,
        description='If the upload should be processed when the import is done (not recommended).',
    )
    process_settings: Reprocess = Field(
        Reprocess(
            rematch_published=True,
            reprocess_existing_entries=True,
            use_original_parser=False,
            add_matched_entries_to_published=True,
            delete_unmatched_published_entries=False,
        ),
        description="""
            When trigger_processing is set to True, these settings control the reprocessing
            behaviour (see the config for `reprocess` for more info). NOTE: reprocessing is
            no longer the recommended method to import bundles.
        """,
    )


class BundleImport(NomadSettings):
    """Controls behaviour related to importing bundles."""

    required_nomad_version: str = Field(
        '1.1.2', description='Minimum  NOMAD version of bundles required for import.'
    )

    default_cli_bundle_import_path: str = Field(
        './bundles',
        description='Default path used when importing bundles using the CLI command.',
    )

    allow_bundles_from_oasis: bool = Field(
        False,
        description='If oasis admins can "push" bundles to this NOMAD deployment.',
    )
    allow_unpublished_bundles_from_oasis: bool = Field(
        False, description='If oasis admins can "push" bundles of unpublished uploads.'
    )

    default_settings: BundleImportSettings = Field(
        BundleImportSettings(),
        description="""
            General default settings.
        """,
    )

    default_settings_cli: BundleImportSettings = Field(
        BundleImportSettings(
            delete_bundle_on_fail=False, delete_bundle_on_success=False
        ),
        description="""
            Additional default settings, applied when importing using the CLI. This allows
            to override some of the settings specified in the general default settings above.
        """,
    )


class Archive(NomadSettings):
    block_size = Field(
        1 * 2**20,
        description='In case of using blocked TOC, this is the size of each block.',
    )
    read_buffer_size = Field(
        1 * 2**20,
        description='GPFS needs at least 256K to achieve decent performance.',
    )
    copy_chunk_size = Field(
        16 * 2**20,
        description="""
        The chunk size of every read of binary data.
        It is used to copy data from one file to another.
        A small value will result in more syscalls, a large value will result in higher peak memory usage.
        """,
    )
    toc_depth = Field(10, description='Depths of table of contents in the archive.')
    use_new_writer = True  # todo: to be removed
    small_obj_optimization_threshold = Field(
        1 * 2**20,
        description="""
        For any child of lists/dicts whose encoded size is smaller than this value, no TOC will be generated.""",
    )
    fast_loading = Field(
        True,
        description="""
        When enabled, this flag determines whether to read the whole dict/list at once
        when a certain mount of children has been visited.
        This reduces the number of syscalls although data may be repeatedly read.
        Otherwise, always read children one by one. This may slow down the loading as more syscalls are needed.
        """,
    )
    fast_loading_threshold = Field(
        0.6,
        description="""
        If the fraction of children that have been visited is less than this threshold, fast loading will be used.
        """,
    )
    trivial_size = Field(
        20,
        description="""
        To identify numerical lists.
        """,
    )


class UnitSystemUnit(StrictSettings):
    definition: str = Field(
        description="""
        The unit definition. Can be a mathematical expression that combines
        several units, e.g. `(kg * m) / s^2`. You should only use units that are
        registered in the NOMAD unit registry (`nomad.units.ureg`).
    """
    )
    locked: Optional[bool] = Field(
        False,
        description='Whether the unit is locked in the unit system it is defined in.',
    )


dimensions = [
    # Base units
    'dimensionless',
    'length',
    'mass',
    'time',
    'current',
    'temperature',
    'luminosity',
    'luminous_flux',
    'substance',
    'angle',
    'information',
    # Derived units with specific name
    'force',
    'energy',
    'power',
    'pressure',
    'charge',
    'resistance',
    'conductance',
    'inductance',
    'magnetic_flux',
    'magnetic_field',
    'frequency',
    'luminance',
    'illuminance',
    'electric_potential',
    'capacitance',
    'activity',
]
dimension_list = '\n'.join([' - ' + str(dim) for dim in dimensions])


class UnitSystem(StrictSettings):
    label: str = Field(
        description='Short, descriptive label used for this unit system.'
    )
    units: Optional[Dict[str, UnitSystemUnit]] = Field(
        description=f"""
        Contains a mapping from each dimension to a unit. If a unit is not
        specified for a dimension, the SI equivalent will be used by default.
        The following dimensions are available:
        {dimension_list}
    """
    )

    @root_validator(pre=True)
    def __dimensions_and_si_defaults(cls, values):  # pylint: disable=no-self-argument
        """Adds SI defaults for dimensions that are missing a unit."""
        units = values.get('units', {})
        from nomad.units import ureg
        from pint import UndefinedUnitError

        # Check that only supported dimensions and units are used
        for key in units.keys():
            if key not in dimensions:
                raise AssertionError(
                    f'Unsupported dimension "{key}" used in a unit system. The supported dimensions are: {dimensions}.'
                )

        # Fill missing units with SI defaults
        SI = {
            'dimensionless': 'dimensionless',
            'length': 'm',
            'mass': 'kg',
            'time': 's',
            'current': 'A',
            'temperature': 'K',
            'luminosity': 'cd',
            'luminous_flux': 'lm',
            'substance': 'mol',
            'angle': 'rad',
            'information': 'bit',
            'force': 'N',
            'energy': 'J',
            'power': 'W',
            'pressure': 'Pa',
            'charge': 'C',
            'resistance': 'Ω',
            'conductance': 'S',
            'inductance': 'H',
            'magnetic_flux': 'Wb',
            'magnetic_field': 'T',
            'frequency': 'Hz',
            'luminance': 'nit',
            'illuminance': 'lx',
            'electric_potential': 'V',
            'capacitance': 'F',
            'activity': 'kat',
        }
        for dimension in dimensions:
            if dimension not in units:
                units[dimension] = {'definition': SI[dimension]}

        # Check that units are available in registry, and thus also in the GUI.
        for value in units.values():
            definition = value['definition']
            try:
                ureg.Unit(definition)
            except UndefinedUnitError as e:
                raise AssertionError(
                    f'Unsupported unit "{definition}" used in a unit registry.'
                )

        values['units'] = units

        return values


class UnitSystems(OptionsSingle):
    """Controls the available unit systems."""

    options: Optional[Dict[str, UnitSystem]] = Field(
        description='Contains the available unit systems.'
    )


class Theme(StrictSettings):
    """Theme and identity settings."""

    title: str = Field(description='Site name in the browser tab.')


class NORTHUI(StrictSettings):
    """NORTH (NOMAD Remote Tools Hub) UI configuration."""

    enabled: bool = Field(
        True,
        description="""
        Whether the NORTH tools are available in the UI.
        The default value is read from the root-level NORTH configuration.
    """,
    )


class Card(StrictSettings):
    """Definition for a card shown in the entry overview page."""

    error: str = Field(
        description='The error message to show if an error is encountered within the card.'
    )


class Cards(Options):
    """Contains the overview page card definitions and controls their visibility."""

    options: Optional[Dict[str, Card]] = Field(
        description='Contains the available card options.'
    )


class Entry(StrictSettings):
    """Controls the entry visualization."""

    cards: Cards = Field(
        description='Controls the cards that are displayed on the entry overview page.'
    )


class Pagination(StrictSettings):
    order_by: str = Field('upload_create_time', description='Field used for sorting.')
    order: str = Field('desc', description='Sorting order.')
    page_size: int = Field(20, description='Number of results on each page.')


class ModeEnum(str, Enum):
    STANDARD = 'standard'
    SCIENTIFIC = 'scientific'
    SEPARATORS = 'separators'


class Format(StrictSettings):
    """Value formatting options."""

    decimals: int = Field(3, description='Number of decimals to show for numbers.')
    mode: ModeEnum = Field('standard', description='Display mode for numbers.')


class AlignEnum(str, Enum):
    LEFT = 'left'
    RIGHT = 'right'
    CENTER = 'center'


class Column(StrictSettings):
    """Option for a column show in the search results."""

    label: Optional[str] = Field(
        description='Label shown in the header. Defaults to the quantity name.'
    )
    align: AlignEnum = Field(AlignEnum.LEFT, description='Alignment in the table.')
    unit: Optional[str] = Field(
        description="""
        Unit to convert to when displaying. If not given will be displayed in
        using the default unit in the active unit system.
    """
    )
    format: Optional[Format] = Field(
        description='Controls the formatting of the values.'
    )


class Columns(OptionsMulti):
    """
    Contains column definitions, controls their availability and specifies the default
    selection.
    """

    options: Optional[Dict[str, Column]] = Field(
        description="""
        All available column options. Note here that the key must correspond to a
        quantity path that exists in the metadata.
    """
    )


class RowActions(StrictSettings):
    """Controls the visualization of row actions that are shown at the end of each row."""

    enabled: bool = Field(True, description='Whether to enable row actions. ')


class RowDetails(StrictSettings):
    """
    Controls the visualization of row details that are shown upon pressing the row and
    contain basic details about the entry.
    """

    enabled: bool = Field(True, description='Whether to show row details.')


class RowSelection(StrictSettings):
    """
    Controls the selection of rows. If enabled, rows can be selected and additional
    actions performed on them.
    """

    enabled: bool = Field(True, description='Whether to show the row selection.')


class Rows(StrictSettings):
    """Controls the visualization of rows in the search results."""

    actions: RowActions
    details: RowDetails
    selection: RowSelection


class FilterMenuActionEnum(str, Enum):
    CHECKBOX = 'checkbox'


class FilterMenuAction(StrictSettings):
    """Contains definition for an action in the filter menu."""

    type: FilterMenuActionEnum = Field(description='Action type.')
    label: str = Field(description='Label to show.')


class FilterMenuActionCheckbox(FilterMenuAction):
    """Contains definition for checkbox action in the filter menu."""

    quantity: str = Field(description='Targeted quantity')


class FilterMenuActions(Options):
    """Contains filter menu action definitions and controls their availability."""

    options: Optional[Dict[str, FilterMenuActionCheckbox]] = Field(
        description='Contains options for filter menu actions.'
    )


class FilterMenuSizeEnum(str, Enum):
    S = 's'
    M = 'm'
    L = 'l'
    XL = 'xl'


class FilterMenu(StrictSettings):
    """Defines the layout and functionality for a filter menu."""

    label: Optional[str] = Field(description='Menu label to show in the UI.')
    level: Optional[int] = Field(0, description='Indentation level of the menu.')
    size: Optional[FilterMenuSizeEnum] = Field(
        FilterMenuSizeEnum.S, description='Width of the menu.'
    )
    actions: Optional[FilterMenuActions]


class FilterMenus(Options):
    """Contains filter menu definitions and controls their availability."""

    options: Optional[Dict[str, FilterMenu]] = Field(
        description='Contains the available filter menu options.'
    )


class Filters(OptionsGlob):
    """Controls the availability of filters in the app. Filters are pieces of
    (meta)info than can be queried in the search interface of the app, but also
    targeted in the rest of the app configuration. The `include` and `exlude`
    attributes can use glob syntax to target metainfo, e.g. `results.*` or
    `*.#myschema.schema.MySchema`.
    """

    include: Optional[List[str]] = Field(
        description="""
        List of included options. Supports glob/wildcard syntax.
    """
    )
    exclude: Optional[List[str]] = Field(
        description="""
        List of excluded options. Supports glob/wildcard syntax. Has higher precedence than include.
    """
    )


class SearchSyntaxes(StrictSettings):
    """Controls the availability of different search syntaxes. These syntaxes
    determine how raw user input in e.g. the search bar is parsed into queries
    supported by the API.

    Currently you can only exclude items. By default, the following options are
    included:

     - `existence`: Used to query for the existence of a specific metainfo field in the data.
     - `equality`: Used to query for a specific value with exact match.
     - `range_bounded`: Queries values that are between two numerical limits, inclusive or exclusive.
     - `range_half_bounded`: Queries values that are above/below a numerical limit, inclusive or exclusive.
     - `free_text`: For inexact, queries. Requires that a set of keywords has been filled in the entry.
    """

    exclude: Optional[List[str]] = Field(
        description="""
        List of excluded options.
    """
    )


class Layout(StrictSettings):
    """Defines widget size and grid positioning for different breakpoints."""

    h: int = Field(description='Height in grid units')
    w: int = Field(description='Width in grid units.')
    x: int = Field(description='Horizontal start location in the grid.')
    y: int = Field(description='Vertical start location in the grid.')
    minH: Optional[int] = Field(3, description='Minimum height in grid units.')
    minW: Optional[int] = Field(3, description='Minimum width in grid units.')


class ScaleEnum(str, Enum):
    POW1 = 'linear'
    POW2 = '1/2'
    POW4 = '1/4'
    POW8 = '1/8'


class BreakpointEnum(str, Enum):
    SM = 'sm'
    MD = 'md'
    LG = 'lg'
    XL = 'xl'
    XXL = 'xxl'


class Axis(StrictSettings):
    """Configuration for a plot axis."""

    title: Optional[str] = Field(description="""Custom title to show for the axis.""")
    unit: Optional[str] = Field(
        description="""Custom unit used for displaying the values."""
    )
    quantity: str = Field(
        description="""
        Path of the targeted quantity. Note that you can most of the features
        JMESPath syntax here to further specify a selection of values. This
        becomes especially useful when dealing with repeated sections or
        statistical values.
        """
    )


class Markers(StrictSettings):
    """Configuration for plot markers."""

    color: Optional[Axis] = Field(
        description='Configures the information source and display options for the marker colors.'
    )


class Widget(StrictSettings):
    """Common configuration for all widgets."""

    type: str = Field(description='Used to identify the widget type.')
    layout: Dict[BreakpointEnum, Layout] = Field(
        description="""
        Defines widget size and grid positioning for different breakpoints. The
        following breakpoints are supported: `sm`, `md`, `lg`, `xl` and `xxl`.
    """
    )


class WidgetTerms(Widget):
    """Terms widget configuration."""

    type: Literal['terms'] = Field(
        description='Set as `terms` to get this widget type.'
    )
    quantity: str = Field(description='Targeted quantity.')
    scale: ScaleEnum = Field(description='Statistics scaling.')
    showinput: bool = Field(True, description='Whether to show text input field.')


class WidgetHistogram(Widget):
    """Histogram widget configuration."""

    type: Literal['histogram'] = Field(
        description='Set as `histogram` to get this widget type.'
    )
    quantity: str = Field(description='Targeted quantity.')
    scale: ScaleEnum = Field(description='Statistics scaling.')
    autorange: bool = Field(
        True,
        description='Whether to automatically set the range according to the data limits.',
    )
    showinput: bool = Field(
        True,
        description='Whether to show input text fields for minimum and maximum value.',
    )
    nbins: int = Field(
        description="""
        Maximum number of histogram bins. Notice that the actual number of bins
        may be smaller if there are fewer data items available.
        """
    )


class WidgetPeriodicTable(Widget):
    """Periodic table widget configuration."""

    type: Literal['periodictable'] = Field(
        description='Set as `periodictable` to get this widget type.'
    )
    quantity: str = Field(description='Targeted quantity.')
    scale: ScaleEnum = Field(description='Statistics scaling.')


class WidgetScatterPlot(Widget):
    """Scatter plot widget configuration."""

    type: Literal['scatterplot'] = Field(
        description='Set as `scatterplot` to get this widget type.'
    )
    x: Union[Axis, str] = Field(
        description='Configures the information source and display options for the x-axis.'
    )
    y: Union[Axis, str] = Field(
        description='Configures the information source and display options for the y-axis.'
    )
    markers: Optional[Markers] = Field(
        description='Configures the information source and display options for the markers.'
    )
    color: Optional[str] = Field(
        description="""
        Quantity used for coloring points. Note that this field is deprecated
        and `markers` should be used instead.
        """
    )
    size: int = Field(
        1000,
        description="""
        Maximum number of entries to fetch. Notice that the actual number may be
        more of less, depending on how many entries exist and how many of the
        requested values each entry contains.
        """,
    )
    autorange: bool = Field(
        True,
        description='Whether to automatically set the range according to the data limits.',
    )

    @root_validator(pre=True)
    def backwards_compatibility(cls, values):
        """Ensures backwards compatibility of x, y, and color."""
        color = values.get('color')
        if color is not None:
            values['markers'] = {'color': {'quantity': color}}
            del values['color']
        x = values.get('x')
        if isinstance(x, str):
            values['x'] = {'quantity': x}
        y = values.get('y')
        if isinstance(y, str):
            values['y'] = {'quantity': y}
        return values


# The 'discriminated union' feature of Pydantic is used here:
# https://docs.pydantic.dev/usage/types/#discriminated-unions-aka-tagged-unions
WidgetAnnotated = Annotated[
    Union[WidgetTerms, WidgetHistogram, WidgetScatterPlot, WidgetPeriodicTable],
    Field(discriminator='type'),
]


class Dashboard(StrictSettings):
    """Dashboard configuration."""

    widgets: List[WidgetAnnotated] = Field(
        description='List of widgets contained in the dashboard.'
    )  # type: ignore


class ResourceEnum(str, Enum):
    ENTRIES = 'entries'
    MATERIALS = 'materials'


class App(StrictSettings):
    """Defines the layout and functionality for an App."""

    label: str = Field(description='Name of the App.')
    path: str = Field(description='Path used in the browser address bar.')
    resource: ResourceEnum = Field('entries', description='Targeted resource.')
    breadcrumb: Optional[str] = Field(
        description='Name displayed in the breadcrumb, by default the label will be used.'
    )
    category: str = Field(
        description='Category used to organize Apps in the explore menu.'
    )
    description: Optional[str] = Field(description='Short description of the App.')
    readme: Optional[str] = Field(
        description='Longer description of the App that can also use markdown.'
    )
    pagination: Pagination = Field(
        Pagination(), description='Default result pagination.'
    )
    columns: Columns = Field(
        description='Controls the columns shown in the results table.'
    )
    rows: Optional[Rows] = Field(
        Rows(
            actions=RowActions(enabled=True),
            details=RowDetails(enabled=True),
            selection=RowSelection(enabled=True),
        ),
        description='Controls the display of entry rows in the results table.',
    )
    filter_menus: FilterMenus = Field(
        description='Filter menus displayed on the left side of the screen.'
    )
    filters: Optional[Filters] = Field(
        Filters(exclude=['mainfile', 'entry_name', 'combine']),
        description='Controls the filters that are available in this app.',
    )
    dashboard: Optional[Dashboard] = Field(description='Default dashboard layout.')
    filters_locked: Optional[dict] = Field(
        description="""
        Fixed query object that is applied for this search context. This filter
        will always be active for this context and will not be displayed to the
        user by default.
        """
    )
    search_syntaxes: Optional[SearchSyntaxes] = Field(
        description='Controls which types of search syntax are available.'
    )


class Apps(Options):
    """Contains App definitions and controls their availability."""

    options: Optional[Dict[str, App]] = Field(
        description='Contains the available app options.'
    )


class ExampleUploads(OptionsBase):
    """Controls the availability of example uploads."""


class UI(StrictSettings):
    """Used to customize the user interface."""

    app_base: str = Field(
        None, description='This is automatically set from the nomad.yaml'
    )
    north_base: str = Field(
        None, description='This is automatically set from the nomad.yaml'
    )
    theme: Theme = Field(
        Theme(**{'title': 'NOMAD'}), description='Controls the site theme and identity.'
    )
    unit_systems: UnitSystems = Field(
        UnitSystems(
            **{
                'selected': 'Custom',
                'options': {
                    'Custom': {
                        'label': 'Custom',
                        'units': {
                            'length': {'definition': 'Å'},
                            'time': {'definition': 'fs'},
                            'energy': {'definition': 'eV'},
                            'pressure': {'definition': 'GPa'},
                            'angle': {'definition': '°'},
                        },
                    },
                    'SI': {
                        'label': 'International System of Units (SI)',
                        'units': {
                            'dimensionless': {
                                'definition': 'dimensionless',
                                'locked': True,
                            },
                            'length': {'definition': 'm', 'locked': True},
                            'mass': {'definition': 'kg', 'locked': True},
                            'time': {'definition': 's', 'locked': True},
                            'current': {'definition': 'A', 'locked': True},
                            'temperature': {'definition': 'K', 'locked': True},
                            'luminosity': {'definition': 'cd', 'locked': True},
                            'luminous_flux': {'definition': 'lm', 'locked': True},
                            'substance': {'definition': 'mol', 'locked': True},
                            'angle': {'definition': 'rad', 'locked': True},
                            'information': {'definition': 'bit', 'locked': True},
                            'force': {'definition': 'N', 'locked': True},
                            'energy': {'definition': 'J', 'locked': True},
                            'power': {'definition': 'W', 'locked': True},
                            'pressure': {'definition': 'Pa', 'locked': True},
                            'charge': {'definition': 'C', 'locked': True},
                            'resistance': {'definition': 'Ω', 'locked': True},
                            'conductance': {'definition': 'S', 'locked': True},
                            'inductance': {'definition': 'H', 'locked': True},
                            'magnetic_flux': {'definition': 'Wb', 'locked': True},
                            'magnetic_field': {'definition': 'T', 'locked': True},
                            'frequency': {'definition': 'Hz', 'locked': True},
                            'luminance': {'definition': 'nit', 'locked': True},
                            'illuminance': {'definition': 'lx', 'locked': True},
                            'electric_potential': {'definition': 'V', 'locked': True},
                            'capacitance': {'definition': 'F', 'locked': True},
                            'activity': {'definition': 'kat', 'locked': True},
                        },
                    },
                    'AU': {
                        'label': 'Hartree atomic units (AU)',
                        'units': {
                            'dimensionless': {
                                'definition': 'dimensionless',
                                'locked': True,
                            },
                            'length': {'definition': 'bohr', 'locked': True},
                            'mass': {'definition': 'm_e', 'locked': True},
                            'time': {
                                'definition': 'atomic_unit_of_time',
                                'locked': True,
                            },
                            'current': {
                                'definition': 'atomic_unit_of_current',
                                'locked': True,
                            },
                            'temperature': {
                                'definition': 'atomic_unit_of_temperature',
                                'locked': True,
                            },
                            'luminosity': {'definition': 'cd', 'locked': False},
                            'luminous_flux': {'definition': 'lm', 'locked': False},
                            'substance': {'definition': 'mol', 'locked': False},
                            'angle': {'definition': 'rad', 'locked': False},
                            'information': {'definition': 'bit', 'locked': False},
                            'force': {
                                'definition': 'atomic_unit_of_force',
                                'locked': True,
                            },
                            'energy': {'definition': 'Ha', 'locked': True},
                            'power': {'definition': 'W', 'locked': False},
                            'pressure': {
                                'definition': 'atomic_unit_of_pressure',
                                'locked': True,
                            },
                            'charge': {'definition': 'C', 'locked': False},
                            'resistance': {'definition': 'Ω', 'locked': False},
                            'conductance': {'definition': 'S', 'locked': False},
                            'inductance': {'definition': 'H', 'locked': False},
                            'magnetic_flux': {'definition': 'Wb', 'locked': False},
                            'magnetic_field': {'definition': 'T', 'locked': False},
                            'frequency': {'definition': 'Hz', 'locked': False},
                            'luminance': {'definition': 'nit', 'locked': False},
                            'illuminance': {'definition': 'lx', 'locked': False},
                            'electric_potential': {'definition': 'V', 'locked': False},
                            'capacitance': {'definition': 'F', 'locked': False},
                            'activity': {'definition': 'kat', 'locked': False},
                        },
                    },
                },
            }
        ),
        description='Controls the available unit systems.',
    )
    entry: Entry = Field(
        Entry(
            **{
                'cards': {
                    'exclude': ['relatedResources'],
                    'options': {
                        'sections': {'error': 'Could not render section card.'},
                        'definitions': {'error': 'Could not render definitions card.'},
                        'nexus': {'error': 'Could not render NeXus card.'},
                        'material': {'error': 'Could not render material card.'},
                        'solarcell': {
                            'error': 'Could not render solar cell properties.'
                        },
                        'heterogeneouscatalyst': {
                            'error': 'Could not render catalyst properties.'
                        },
                        'electronic': {
                            'error': 'Could not render electronic properties.'
                        },
                        'vibrational': {
                            'error': 'Could not render vibrational properties.'
                        },
                        'mechanical': {
                            'error': 'Could not render mechanical properties.'
                        },
                        'thermodynamic': {
                            'error': 'Could not render thermodynamic properties.'
                        },
                        'structural': {
                            'error': 'Could not render structural properties.'
                        },
                        'dynamical': {
                            'error': 'Could not render dynamical properties.'
                        },
                        'geometry_optimization': {
                            'error': 'Could not render geometry optimization.'
                        },
                        'spectroscopic': {
                            'error': 'Could not render spectroscopic properties.'
                        },
                        'history': {'error': 'Could not render history card.'},
                        'workflow': {'error': 'Could not render workflow card.'},
                        'references': {'error': 'Could not render references card.'},
                        'relatedResources': {
                            'error': 'Could not render related resources card.'
                        },
                    },
                }
            }
        ),
        description='Controls the entry visualization.',
    )
    apps: Apps = Field(
        Apps(
            **{
                'exclude': ['heterogeneouscatalyst'],
                'options': {
                    'entries': {
                        'label': 'Entries',
                        'path': 'entries',
                        'category': 'All',
                        'description': 'Search entries across all domains',
                        'readme': inspect.cleandoc(
                            r"""
                        This page allows you to search **entries** within NOMAD.
                        Entries represent any individual data items that have
                        been uploaded to NOMAD, no matter whether they come from
                        theoretical calculations, experiments, lab notebooks or
                        any other source of data. This allows you to perform
                        cross-domain queries, but if you are interested in a
                        specific subfield, you should see if a specific
                        application exists for it in the explore menu to get
                        more details.
                    """
                        ),
                        'columns': {
                            'selected': [
                                'entry_name',
                                'results.material.chemical_formula_hill',
                                'entry_type',
                                'upload_create_time',
                                'authors',
                            ],
                            'options': {
                                'entry_name': {'label': 'Name', 'align': 'left'},
                                'results.material.chemical_formula_hill': {
                                    'label': 'Formula',
                                    'align': 'left',
                                },
                                'entry_type': {'label': 'Entry type', 'align': 'left'},
                                'entry_create_time': {
                                    'label': 'Entry creation time',
                                    'align': 'left',
                                },
                                'upload_name': {
                                    'label': 'Upload name',
                                    'align': 'left',
                                },
                                'upload_id': {'label': 'Upload id', 'align': 'left'},
                                'upload_create_time': {
                                    'label': 'Upload time',
                                    'align': 'left',
                                },
                                'authors': {'label': 'Authors', 'align': 'left'},
                                'results.method.method_name': {'label': 'Method name'},
                                'results.method.simulation.program_name': {
                                    'label': 'Program name'
                                },
                                'results.method.simulation.dft.xc_functional_type': {
                                    'label': 'XC Functional Type'
                                },
                                'results.method.simulation.precision.apw_cutoff': {
                                    'label': 'APW Cutoff'
                                },
                                'results.method.simulation.precision.basis_set': {
                                    'label': 'Basis Set'
                                },
                                'results.method.simulation.precision.k_line_density': {
                                    'label': 'k-line Density'
                                },
                                'results.method.simulation.precision.native_tier': {
                                    'label': 'Code-specific tier'
                                },
                                'results.method.simulation.precision.planewave_cutoff': {
                                    'label': 'Plane-wave cutoff'
                                },
                                'results.material.structural_type': {
                                    'label': 'Dimensionality'
                                },
                                'results.material.symmetry.crystal_system': {
                                    'label': 'Crystal system'
                                },
                                'results.material.symmetry.space_group_symbol': {
                                    'label': 'Space group symbol'
                                },
                                'results.material.symmetry.space_group_number': {
                                    'label': 'Space group number'
                                },
                                'results.eln.lab_ids': {'label': 'Lab IDs'},
                                'results.eln.sections': {'label': 'Sections'},
                                'results.eln.methods': {'label': 'Methods'},
                                'results.eln.tags': {'label': 'Tags'},
                                'results.eln.instruments': {'label': 'Instruments'},
                                'mainfile': {'label': 'Mainfile', 'align': 'left'},
                                'comment': {'label': 'Comment', 'align': 'left'},
                                'references': {'label': 'References', 'align': 'left'},
                                'datasets': {'label': 'Datasets', 'align': 'left'},
                                'published': {'label': 'Access'},
                            },
                        },
                        'filter_menus': {
                            'options': {
                                'material': {'label': 'Material', 'level': 0},
                                'elements': {
                                    'label': 'Elements / Formula',
                                    'level': 1,
                                    'size': 'xl',
                                },
                                'structure': {
                                    'label': 'Structure / Symmetry',
                                    'level': 1,
                                },
                                'method': {'label': 'Method', 'level': 0},
                                'precision': {'label': 'Precision', 'level': 1},
                                'dft': {'label': 'DFT', 'level': 1},
                                'tb': {'label': 'TB', 'level': 1},
                                'gw': {'label': 'GW', 'level': 1},
                                'bse': {'label': 'BSE', 'level': 1},
                                'dmft': {'label': 'DMFT', 'level': 1},
                                'eels': {'label': 'EELS', 'level': 1},
                                'workflow': {'label': 'Workflow', 'level': 0},
                                'molecular_dynamics': {
                                    'label': 'Molecular dynamics',
                                    'level': 1,
                                },
                                'geometry_optimization': {
                                    'label': 'Geometry Optimization',
                                    'level': 1,
                                },
                                'properties': {'label': 'Properties', 'level': 0},
                                'electronic': {'label': 'Electronic', 'level': 1},
                                'vibrational': {'label': 'Vibrational', 'level': 1},
                                'mechanical': {'label': 'Mechanical', 'level': 1},
                                'usecases': {'label': 'Use Cases', 'level': 0},
                                'solarcell': {'label': 'Solar Cells', 'level': 1},
                                'heterogeneouscatalyst': {
                                    'label': 'Heterogeneous Catalysis',
                                    'level': 1,
                                },
                                'author': {
                                    'label': 'Author / Origin / Dataset',
                                    'level': 0,
                                    'size': 'm',
                                },
                                'metadata': {
                                    'label': 'Visibility / IDs / Schema',
                                    'level': 0,
                                },
                                'optimade': {
                                    'label': 'Optimade',
                                    'level': 0,
                                    'size': 'm',
                                },
                            }
                        },
                        'search_syntaxes': {'exclude': ['free_text']},
                    },
                    'calculations': {
                        'label': 'Calculations',
                        'path': 'calculations',
                        'category': 'Theory',
                        'description': 'Search calculations',
                        'readme': inspect.cleandoc(
                            r"""
                        This page allows you to search **calculations** within
                        NOMAD. Calculations typically come from a specific
                        simulation software that uses an approximate model to
                        investigate and report different physical properties.
                    """
                        ),
                        'columns': {
                            'selected': [
                                'results.material.chemical_formula_hill',
                                'results.method.simulation.program_name',
                                'results.method.method_name',
                                'results.method.simulation.dft.xc_functional_type',
                                'upload_create_time',
                                'authors',
                            ],
                            'options': {
                                'results.material.chemical_formula_hill': {
                                    'label': 'Formula',
                                    'align': 'left',
                                },
                                'results.method.simulation.program_name': {
                                    'label': 'Program name'
                                },
                                'results.method.method_name': {'label': 'Method name'},
                                'results.method.simulation.dft.xc_functional_type': {
                                    'label': "Jacob's ladder"
                                },
                                'upload_create_time': {
                                    'label': 'Upload time',
                                    'align': 'left',
                                },
                                'authors': {'label': 'Authors', 'align': 'left'},
                                'results.method.simulation.precision.apw_cutoff': {
                                    'label': 'APW Cutoff'
                                },
                                'results.method.simulation.precision.basis_set': {
                                    'label': 'Basis Set'
                                },
                                'results.method.simulation.precision.k_line_density': {
                                    'label': 'k-line Density'
                                },
                                'results.method.simulation.precision.native_tier': {
                                    'label': 'Code-specific tier'
                                },
                                'results.method.simulation.precision.planewave_cutoff': {
                                    'label': 'Plane-wave cutoff'
                                },
                                'results.material.structural_type': {
                                    'label': 'Dimensionality'
                                },
                                'results.material.symmetry.crystal_system': {
                                    'label': 'Crystal system'
                                },
                                'results.material.symmetry.space_group_symbol': {
                                    'label': 'Space group symbol'
                                },
                                'results.material.symmetry.space_group_number': {
                                    'label': 'Space group number'
                                },
                                'entry_name': {'label': 'Name', 'align': 'left'},
                                'mainfile': {'label': 'Mainfile', 'align': 'left'},
                                'comment': {'label': 'Comment', 'align': 'left'},
                                'references': {'label': 'References', 'align': 'left'},
                                'datasets': {'label': 'Datasets', 'align': 'left'},
                                'published': {'label': 'Access'},
                            },
                        },
                        'filter_menus': {
                            'options': {
                                'material': {'label': 'Material', 'level': 0},
                                'elements': {
                                    'label': 'Elements / Formula',
                                    'level': 1,
                                    'size': 'xl',
                                },
                                'structure': {
                                    'label': 'Structure / Symmetry',
                                    'level': 1,
                                },
                                'method': {'label': 'Method', 'level': 0},
                                'precision': {'label': 'Precision', 'level': 1},
                                'dft': {'label': 'DFT', 'level': 1},
                                'tb': {'label': 'TB', 'level': 1},
                                'gw': {'label': 'GW', 'level': 1},
                                'bse': {'label': 'BSE', 'level': 1},
                                'dmft': {'label': 'DMFT', 'level': 1},
                                'workflow': {'label': 'Workflow', 'level': 0},
                                'molecular_dynamics': {
                                    'label': 'Molecular dynamics',
                                    'level': 1,
                                },
                                'geometry_optimization': {
                                    'label': 'Geometry Optimization',
                                    'level': 1,
                                },
                                'properties': {'label': 'Properties', 'level': 0},
                                'electronic': {'label': 'Electronic', 'level': 1},
                                'vibrational': {'label': 'Vibrational', 'level': 1},
                                'mechanical': {'label': 'Mechanical', 'level': 1},
                                'author': {
                                    'label': 'Author / Origin / Dataset',
                                    'level': 0,
                                    'size': 'm',
                                },
                                'metadata': {
                                    'label': 'Visibility / IDs / Schema',
                                    'level': 0,
                                },
                                'optimade': {
                                    'label': 'Optimade',
                                    'level': 0,
                                    'size': 'm',
                                },
                            }
                        },
                        'dashboard': {
                            'widgets': [
                                {
                                    'type': 'periodictable',
                                    'scale': 'linear',
                                    'quantity': 'results.material.elements',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 9,
                                            'w': 13,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 11,
                                            'w': 14,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 11,
                                            'w': 14,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 8,
                                            'w': 12,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 8,
                                            'w': 12,
                                            'y': 0,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'terms',
                                    'showinput': True,
                                    'scale': 'linear',
                                    'quantity': 'results.material.symmetry.space_group_symbol',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 9,
                                            'w': 6,
                                            'y': 0,
                                            'x': 30,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 5,
                                            'x': 24,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 5,
                                            'y': 6,
                                            'x': 19,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 8,
                                            'x': 12,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 13,
                                            'x': 6,
                                        },
                                    },
                                },
                                {
                                    'type': 'terms',
                                    'showinput': False,
                                    'scale': '1/8',
                                    'quantity': 'results.material.structural_type',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 9,
                                            'w': 6,
                                            'y': 0,
                                            'x': 19,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 11,
                                            'w': 5,
                                            'y': 0,
                                            'x': 19,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 5,
                                            'y': 0,
                                            'x': 19,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 8,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 8,
                                            'x': 6,
                                        },
                                    },
                                },
                                {
                                    'type': 'terms',
                                    'showinput': True,
                                    'scale': '1/4',
                                    'quantity': 'results.method.simulation.program_name',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 9,
                                            'w': 6,
                                            'y': 0,
                                            'x': 13,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 11,
                                            'w': 5,
                                            'y': 0,
                                            'x': 14,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 5,
                                            'y': 0,
                                            'x': 14,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 8,
                                            'w': 6,
                                            'y': 0,
                                            'x': 12,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 8,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'terms',
                                    'showinput': False,
                                    'scale': 'linear',
                                    'quantity': 'results.material.symmetry.crystal_system',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 9,
                                            'w': 5,
                                            'y': 0,
                                            'x': 25,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 0,
                                            'x': 24,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 5,
                                            'y': 6,
                                            'x': 14,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 8,
                                            'x': 6,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 13,
                                            'x': 0,
                                        },
                                    },
                                },
                            ],
                        },
                        'filters_locked': {
                            'quantities': 'results.method.simulation.program_name',
                        },
                        'search_syntaxes': {'exclude': ['free_text']},
                    },
                    'materials': {
                        'label': 'Materials',
                        'path': 'materials',
                        'resource': 'materials',
                        'category': 'Theory',
                        'description': 'Search materials that are identified from calculations',
                        'readme': inspect.cleandoc(
                            r"""
                        This page allows you to search **materials** within
                        NOMAD. NOMAD can often automatically detect the material
                        from individual calculations that contain the full
                        atomistic structure and can then group the data by using
                        these detected materials. This allows you to search
                        individual materials which have properties that are
                        aggregated from several entries. Following the link for
                        a specific material will take you to the corresponding
                        [NOMAD Encyclopedia](https://nomad-lab.eu/prod/rae/encyclopedia/#/search)
                        page for that material. NOMAD Encyclopedia is a service
                        that is specifically oriented towards materials property
                        exploration.

                        Notice that by default the properties that you search
                        can be combined from several different entries. If
                        instead you wish to search for a material with an
                        individual entry fullfilling your search criteria,
                        uncheck the **combine results from several
                        entries**-checkbox.
                    """
                        ),
                        'pagination': {
                            'order_by': 'chemical_formula_hill',
                            'order': 'asc',
                        },
                        'columns': {
                            'selected': [
                                'chemical_formula_hill',
                                'structural_type',
                                'symmetry.structure_name',
                                'symmetry.space_group_number',
                                'symmetry.crystal_system',
                            ],
                            'options': {
                                'chemical_formula_hill': {
                                    'label': 'Formula',
                                    'align': 'left',
                                },
                                'structural_type': {'label': 'Dimensionality'},
                                'symmetry.structure_name': {'label': 'Structure name'},
                                'symmetry.space_group_number': {
                                    'label': 'Space group number'
                                },
                                'symmetry.crystal_system': {'label': 'Crystal system'},
                                'symmetry.space_group_symbol': {
                                    'label': 'Space group symbol'
                                },
                                'material_id': {'label': 'Material ID'},
                            },
                        },
                        'rows': {
                            'actions': {'enabled': True},
                            'details': {'enabled': False},
                            'selection': {'enabled': False},
                        },
                        'filter_menus': {
                            'options': {
                                'material': {'label': 'Material', 'level': 0},
                                'elements': {
                                    'label': 'Elements / Formula',
                                    'level': 1,
                                    'size': 'xl',
                                },
                                'structure': {
                                    'label': 'Structure / Symmetry',
                                    'level': 1,
                                },
                                'method': {'label': 'Method', 'level': 0},
                                'dft': {'label': 'DFT', 'level': 1},
                                'tb': {'label': 'TB', 'level': 1},
                                'gw': {'label': 'GW', 'level': 1},
                                'bse': {'label': 'BSE', 'level': 1},
                                'dmft': {'label': 'DMFT', 'level': 1},
                                'workflow': {'label': 'Workflow', 'level': 0},
                                'molecular_dynamics': {
                                    'label': 'Molecular dynamics',
                                    'level': 1,
                                },
                                'geometry_optimization': {
                                    'label': 'Geometry Optimization',
                                    'level': 1,
                                },
                                'properties': {'label': 'Properties', 'level': 0},
                                'electronic': {'label': 'Electronic', 'level': 1},
                                'vibrational': {'label': 'Vibrational', 'level': 1},
                                'mechanical': {'label': 'Mechanical', 'level': 1},
                                'author': {
                                    'label': 'Author / Origin / Dataset',
                                    'level': 0,
                                    'size': 'm',
                                },
                                'metadata': {
                                    'label': 'Visibility / IDs / Schema',
                                    'level': 0,
                                },
                                'optimade': {
                                    'label': 'Optimade',
                                    'level': 0,
                                    'size': 'm',
                                },
                                'combine': {
                                    'actions': {
                                        'options': {
                                            'combine': {
                                                'type': 'checkbox',
                                                'label': 'Combine results from several entries',
                                                'quantity': 'combine',
                                            }
                                        }
                                    }
                                },
                            }
                        },
                        'filters': {'exclude': ['mainfile', 'entry_name']},
                        'search_syntaxes': {'exclude': ['free_text']},
                    },
                    'eln': {
                        'label': 'ELN',
                        'path': 'eln',
                        'category': 'Experiment',
                        'description': 'Search electronic lab notebooks',
                        'readme': inspect.cleandoc(
                            r"""
                        This page allows you to specifically seach **electronic
                        lab notebooks (ELNs)** within NOMAD.  It is very similar
                        to the entries search, but with a reduced filter set and
                        specialized arrangement of default columns.
                    """
                        ),
                        'columns': {
                            'selected': [
                                'entry_name',
                                'entry_type',
                                'upload_create_time',
                                'authors',
                            ],
                            'options': {
                                'entry_name': {'label': 'Name', 'align': 'left'},
                                'entry_type': {'label': 'Entry type', 'align': 'left'},
                                'upload_create_time': {
                                    'label': 'Upload time',
                                    'align': 'left',
                                },
                                'authors': {'label': 'Authors', 'align': 'left'},
                                'results.material.chemical_formula_hill': {
                                    'label': 'Formula',
                                    'align': 'left',
                                },
                                'results.method.method_name': {'label': 'Method name'},
                                'results.eln.lab_ids': {'label': 'Lab IDs'},
                                'results.eln.sections': {'label': 'Sections'},
                                'results.eln.methods': {'label': 'Methods'},
                                'results.eln.tags': {'label': 'Tags'},
                                'results.eln.instruments': {'label': 'Instruments'},
                                'mainfile': {'label': 'Mainfile', 'align': 'left'},
                                'comment': {'label': 'Comment', 'align': 'left'},
                                'references': {'label': 'References', 'align': 'left'},
                                'datasets': {'label': 'Datasets', 'align': 'left'},
                                'published': {'label': 'Access'},
                            },
                        },
                        'filter_menus': {
                            'options': {
                                'material': {'label': 'Material', 'level': 0},
                                'elements': {
                                    'label': 'Elements / Formula',
                                    'level': 1,
                                    'size': 'xl',
                                },
                                'eln': {'label': 'Electronic Lab Notebook', 'level': 0},
                                'custom_quantities': {
                                    'label': 'User Defined Quantities',
                                    'level': 0,
                                    'size': 'l',
                                },
                                'author': {
                                    'label': 'Author / Origin / Dataset',
                                    'level': 0,
                                    'size': 'm',
                                },
                                'metadata': {
                                    'label': 'Visibility / IDs / Schema',
                                    'level': 0,
                                },
                                'optimade': {
                                    'label': 'Optimade',
                                    'level': 0,
                                    'size': 'm',
                                },
                            }
                        },
                        'filters_locked': {'quantities': 'data'},
                    },
                    'eels': {
                        'label': 'EELS',
                        'path': 'eels',
                        'category': 'Experiment',
                        'description': 'Search electron energy loss spectroscopy experiments',
                        'readme': inspect.cleandoc(
                            r"""
                        This page allows you to spefically search **Electron
                        Energy Loss Spectroscopy (EELS) experiments** within
                        NOMAD. It is similar to the entries search, but with a
                        reduced filter set and specialized arrangement of
                        default columns.
                    """
                        ),
                        'columns': {
                            'selected': [
                                'results.material.chemical_formula_hill',
                                'results.properties.spectroscopic.spectra.provenance.eels.detector_type',
                                'results.properties.spectroscopic.spectra.provenance.eels.resolution',
                                'upload_create_time',
                                'authors',
                            ],
                            'options': {
                                'results.material.chemical_formula_hill': {
                                    'label': 'Formula',
                                    'align': 'left',
                                },
                                'results.properties.spectroscopic.spectra.provenance.eels.detector_type': {
                                    'label': 'Detector type'
                                },
                                'results.properties.spectroscopic.spectra.provenance.eels.resolution': {
                                    'label': 'Resolution'
                                },
                                'upload_create_time': {
                                    'label': 'Upload time',
                                    'align': 'left',
                                },
                                'authors': {'label': 'Authors', 'align': 'left'},
                                'results.properties.spectroscopic.spectra.provenance.eels.min_energy': {},
                                'results.properties.spectroscopic.spectra.provenance.eels.max_energy': {},
                                'entry_name': {'label': 'Name', 'align': 'left'},
                                'entry_type': {'label': 'Entry type', 'align': 'left'},
                                'mainfile': {'label': 'Mainfile', 'align': 'left'},
                                'comment': {'label': 'Comment', 'align': 'left'},
                                'references': {'label': 'References', 'align': 'left'},
                                'datasets': {'label': 'Datasets', 'align': 'left'},
                                'published': {'label': 'Access'},
                            },
                        },
                        'filter_menus': {
                            'options': {
                                'material': {'label': 'Material', 'level': 0},
                                'elements': {
                                    'label': 'Elements / Formula',
                                    'level': 1,
                                    'size': 'xl',
                                },
                                'method': {'label': 'Method', 'level': 0},
                                'eels': {'label': 'EELS', 'level': 1},
                                'author': {
                                    'label': 'Author / Origin / Dataset',
                                    'level': 0,
                                    'size': 'm',
                                },
                                'metadata': {
                                    'label': 'Visibility / IDs / Schema',
                                    'level': 0,
                                },
                                'optimade': {
                                    'label': 'Optimade',
                                    'level': 0,
                                    'size': 'm',
                                },
                            }
                        },
                        'filters_locked': {'results.method.method_name': 'EELS'},
                        'search_syntaxes': {'exclude': ['free_text']},
                    },
                    'solarcells': {
                        'label': 'Solar Cells',
                        'path': 'solarcells',
                        'category': 'Use Cases',
                        'description': 'Search solar cells',
                        'readme': inspect.cleandoc(
                            r"""
                        This page allows you to search **solar cell data**
                        within NOMAD. The filter menu on the left and the shown
                        default columns are specifically designed for solar cell
                        exploration. The dashboard directly shows useful
                        interactive statistics about the data.
                    """
                        ),
                        'filters': {
                            'include': [
                                '*#perovskite_solar_cell_database.schema.PerovskiteSolarCell'
                            ],
                            'exclude': ['mainfile', 'entry_name', 'combine'],
                        },
                        'pagination': {
                            'order_by': 'results.properties.optoelectronic.solar_cell.efficiency',
                        },
                        'dashboard': {
                            'widgets': [
                                {
                                    'type': 'periodictable',
                                    'scale': 'linear',
                                    'quantity': 'results.material.elements',
                                    'layout': {
                                        'xxl': {
                                            'minH': 8,
                                            'minW': 12,
                                            'h': 8,
                                            'w': 13,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'xl': {
                                            'minH': 8,
                                            'minW': 12,
                                            'h': 8,
                                            'w': 12,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'lg': {
                                            'minH': 8,
                                            'minW': 12,
                                            'h': 8,
                                            'w': 12,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 8,
                                            'minW': 12,
                                            'h': 8,
                                            'w': 12,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 8,
                                            'minW': 12,
                                            'h': 8,
                                            'w': 12,
                                            'y': 16,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'scatterplot',
                                    'autorange': True,
                                    'size': 1000,
                                    'x': {
                                        'quantity': 'results.properties.optoelectronic.solar_cell.open_circuit_voltage'
                                    },
                                    'y': {
                                        'quantity': 'results.properties.optoelectronic.solar_cell.efficiency',
                                        'title': 'Efficiency (%)',
                                    },
                                    'markers': {
                                        'color': {
                                            'quantity': 'results.properties.optoelectronic.solar_cell.short_circuit_current_density',
                                            'unit': 'mA/cm^2',
                                        }
                                    },
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 8,
                                            'w': 12,
                                            'y': 0,
                                            'x': 24,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 8,
                                            'w': 9,
                                            'y': 0,
                                            'x': 12,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 12,
                                            'y': 8,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 9,
                                            'y': 8,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 0,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'scatterplot',
                                    'autorange': True,
                                    'size': 1000,
                                    'y': {
                                        'quantity': 'results.properties.optoelectronic.solar_cell.efficiency',
                                        'title': 'Efficiency (%)',
                                    },
                                    'x': {
                                        'quantity': 'results.properties.optoelectronic.solar_cell.open_circuit_voltage',
                                    },
                                    'markers': {
                                        'color': {
                                            'quantity': 'results.properties.optoelectronic.solar_cell.device_architecture',
                                        }
                                    },
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 8,
                                            'w': 11,
                                            'y': 0,
                                            'x': 13,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 8,
                                            'w': 9,
                                            'y': 0,
                                            'x': 21,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 12,
                                            'y': 14,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 9,
                                            'y': 8,
                                            'x': 9,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 0,
                                            'x': 6,
                                        },
                                    },
                                },
                                {
                                    'type': 'terms',
                                    'showinput': True,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.optoelectronic.solar_cell.device_stack',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 8,
                                            'x': 14,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 8,
                                            'x': 14,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 0,
                                            'x': 12,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 6,
                                            'y': 4,
                                            'x': 12,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 4,
                                            'y': 10,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'histogram',
                                    'autorange': True,
                                    'nbins': 30,
                                    'scale': '1/4',
                                    'quantity': 'results.properties.optoelectronic.solar_cell.illumination_intensity',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 3,
                                            'w': 8,
                                            'y': 8,
                                            'x': 0,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 3,
                                            'w': 8,
                                            'y': 11,
                                            'x': 0,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 12,
                                            'y': 12,
                                            'x': 12,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 3,
                                            'w': 8,
                                            'y': 17,
                                            'x': 10,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 3,
                                            'w': 8,
                                            'y': 13,
                                            'x': 4,
                                        },
                                    },
                                },
                                {
                                    'type': 'terms',
                                    'showinput': True,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.optoelectronic.solar_cell.absorber_fabrication',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 8,
                                            'x': 8,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 8,
                                            'x': 8,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 0,
                                            'x': 18,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 6,
                                            'y': 0,
                                            'x': 12,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 4,
                                            'y': 5,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'histogram',
                                    'showinput': False,
                                    'autorange': False,
                                    'nbins': 30,
                                    'scale': '1/4',
                                    'quantity': 'results.properties.electronic.band_structure_electronic.band_gap.value',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 11,
                                            'x': 0,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 8,
                                            'x': 0,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 12,
                                            'y': 16,
                                            'x': 12,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 14,
                                            'x': 10,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 10,
                                            'x': 4,
                                        },
                                    },
                                },
                                {
                                    'type': 'terms',
                                    'showinput': True,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.optoelectronic.solar_cell.electron_transport_layer',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 8,
                                            'x': 20,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 5,
                                            'y': 8,
                                            'x': 25,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 6,
                                            'x': 18,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 5,
                                            'y': 14,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 4,
                                            'y': 5,
                                            'x': 4,
                                        },
                                    },
                                },
                                {
                                    'type': 'terms',
                                    'showinput': True,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.optoelectronic.solar_cell.hole_transport_layer',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 8,
                                            'x': 26,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 5,
                                            'y': 8,
                                            'x': 20,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 6,
                                            'x': 12,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 5,
                                            'y': 14,
                                            'x': 5,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 4,
                                            'y': 5,
                                            'x': 8,
                                        },
                                    },
                                },
                            ]
                        },
                        'columns': {
                            'selected': [
                                'results.material.chemical_formula_descriptive',
                                'results.properties.optoelectronic.solar_cell.efficiency',
                                'results.properties.optoelectronic.solar_cell.open_circuit_voltage',
                                'results.properties.optoelectronic.solar_cell.short_circuit_current_density',
                                'results.properties.optoelectronic.solar_cell.fill_factor',
                                'references',
                            ],
                            'options': {
                                'results.material.chemical_formula_descriptive': {
                                    'label': 'Descriptive Formula',
                                    'align': 'left',
                                },
                                'results.properties.optoelectronic.solar_cell.efficiency': {
                                    'label': 'Efficiency (%)',
                                    'format': {
                                        'decimals': 2,
                                        'mode': 'standard',
                                    },
                                },
                                'results.properties.optoelectronic.solar_cell.open_circuit_voltage': {
                                    'label': 'Open circuit voltage',
                                    'unit': 'V',
                                    'format': {
                                        'decimals': 3,
                                        'mode': 'standard',
                                    },
                                },
                                'results.properties.optoelectronic.solar_cell.short_circuit_current_density': {
                                    'label': 'Short circuit current density',
                                    'unit': 'A/m**2',
                                    'format': {
                                        'decimals': 3,
                                        'mode': 'standard',
                                    },
                                },
                                'results.properties.optoelectronic.solar_cell.fill_factor': {
                                    'label': 'Fill factor',
                                    'format': {
                                        'decimals': 3,
                                        'mode': 'standard',
                                    },
                                },
                                'references': {'label': 'References', 'align': 'left'},
                                'results.material.chemical_formula_hill': {
                                    'label': 'Formula',
                                    'align': 'left',
                                },
                                'results.material.structural_type': {
                                    'label': 'Dimensionality'
                                },
                                'results.properties.optoelectronic.solar_cell.illumination_intensity': {
                                    'label': 'Illum. intensity',
                                    'unit': 'W/m**2',
                                    'format': {'decimals': 3, 'mode': 'standard'},
                                },
                                'results.eln.lab_ids': {'label': 'Lab IDs'},
                                'results.eln.sections': {'label': 'Sections'},
                                'results.eln.methods': {'label': 'Methods'},
                                'results.eln.tags': {'label': 'Tags'},
                                'results.eln.instruments': {'label': 'Instruments'},
                                'entry_name': {'label': 'Name', 'align': 'left'},
                                'entry_type': {'label': 'Entry type', 'align': 'left'},
                                'mainfile': {'label': 'Mainfile', 'align': 'left'},
                                'upload_create_time': {
                                    'label': 'Upload time',
                                    'align': 'left',
                                },
                                'authors': {'label': 'Authors', 'align': 'left'},
                                'comment': {'label': 'Comment', 'align': 'left'},
                                'datasets': {'label': 'Datasets', 'align': 'left'},
                                'published': {'label': 'Access'},
                            },
                        },
                        'filter_menus': {
                            'options': {
                                'material': {'label': 'Absorber Material', 'level': 0},
                                'elements': {
                                    'label': 'Elements / Formula',
                                    'level': 1,
                                    'size': 'xl',
                                },
                                'structure': {
                                    'label': 'Structure / Symmetry',
                                    'level': 1,
                                },
                                'electronic': {
                                    'label': 'Electronic Properties',
                                    'level': 0,
                                },
                                'solarcell': {
                                    'label': 'Solar Cell Properties',
                                    'level': 0,
                                },
                                'eln': {'label': 'Electronic Lab Notebook', 'level': 0},
                                'custom_quantities': {
                                    'label': 'User Defined Quantities',
                                    'level': 0,
                                    'size': 'l',
                                },
                                'author': {
                                    'label': 'Author / Origin / Dataset',
                                    'level': 0,
                                    'size': 'm',
                                },
                                'metadata': {
                                    'label': 'Visibility / IDs / Schema',
                                    'level': 0,
                                },
                                'optimade': {
                                    'label': 'Optimade',
                                    'level': 0,
                                    'size': 'm',
                                },
                            }
                        },
                        'filters_locked': {
                            'sections': 'nomad.datamodel.results.SolarCell'
                        },
                        'search_syntaxes': {'exclude': ['free_text']},
                    },
                    'heterogeneouscatalyst': {
                        'label': 'Heterogeneous Catalysis',
                        'path': 'heterogeneouscatalyst',
                        'category': 'Use Cases',
                        'description': 'Search heterogeneous catalysts',
                        'readme': inspect.cleandoc(
                            r"""
                        This page allows you to search **catalyst and catalysis data**
                        within NOMAD. The filter menu on the left and the shown
                        default columns are specifically designed for Heterogeneous Catalyst
                        exploration. The dashboard directly shows useful
                        interactive statistics about the data.
                    """
                        ),
                        'pagination': {
                            'order_by': 'upload_create_time',
                            'order': 'asc',
                        },
                        'dashboard': {
                            'widgets': [
                                {
                                    'type': 'periodictable',
                                    'scale': 'linear',
                                    'quantity': 'results.material.elements',
                                    'layout': {
                                        'xxl': {
                                            'minH': 8,
                                            'minW': 12,
                                            'h': 8,
                                            'w': 12,
                                            'y': 5,
                                            'x': 0,
                                        },
                                        'xl': {
                                            'minH': 8,
                                            'minW': 12,
                                            'h': 8,
                                            'w': 12,
                                            'y': 5,
                                            'x': 0,
                                        },
                                        'lg': {
                                            'minH': 8,
                                            'minW': 12,
                                            'h': 8,
                                            'w': 12,
                                            'y': 6,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 8,
                                            'minW': 12,
                                            'h': 8,
                                            'w': 12,
                                            'y': 5,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 8,
                                            'minW': 12,
                                            'h': 8,
                                            'w': 12,
                                            'y': 5,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'terms',
                                    'showinput': True,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.catalytic.reactivity.reactants.name',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 0,
                                            'x': 6,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 4,
                                            'y': 0,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'terms',
                                    'showinput': True,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.catalytic.reactivity.reaction_name',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 0,
                                            'x': 12,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 0,
                                            'x': 12,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 0,
                                            'x': 12,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 4,
                                            'y': 0,
                                            'x': 8,
                                        },
                                    },
                                },
                                {
                                    'type': 'terms',
                                    'showinput': True,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.catalytic.reactivity.products.name',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 0,
                                            'x': 12,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 0,
                                            'x': 6,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 6,
                                            'y': 0,
                                            'x': 6,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 6,
                                            'y': 0,
                                            'x': 6,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 4,
                                            'y': 0,
                                            'x': 4,
                                        },
                                    },
                                },
                                {
                                    'type': 'terms',
                                    'showinput': True,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.catalytic.catalyst_synthesis.preparation_method',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 6,
                                            'y': 5,
                                            'x': 12,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 6,
                                            'y': 5,
                                            'x': 12,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 6,
                                            'y': 6,
                                            'x': 12,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 6,
                                            'y': 5,
                                            'x': 12,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 3,
                                            'w': 4,
                                            'y': 13,
                                            'x': 8,
                                        },
                                    },
                                },
                                {
                                    'type': 'terms',
                                    'showinput': True,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.catalytic.catalyst_synthesis.catalyst_type',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 6,
                                            'y': 9,
                                            'x': 12,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 6,
                                            'y': 9,
                                            'x': 12,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 6,
                                            'y': 10,
                                            'x': 12,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 6,
                                            'y': 9,
                                            'x': 12,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 3,
                                            'w': 4,
                                            'y': 16,
                                            'x': 8,
                                        },
                                    },
                                },
                                {
                                    'type': 'histogram',
                                    'showinput': False,
                                    'autorange': False,
                                    'nbins': 30,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.catalytic.reactivity.test_temperatures',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 9,
                                            'y': 13,
                                            'x': 0,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 9,
                                            'y': 13,
                                            'x': 0,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 9,
                                            'y': 14,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 9,
                                            'y': 13,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 13,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'histogram',
                                    'showinput': False,
                                    'autorange': False,
                                    'nbins': 30,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.catalytic.reactivity.gas_hourly_space_velocity',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 9,
                                            'y': 16,
                                            'x': 0,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 9,
                                            'y': 17,
                                            'x': 0,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 9,
                                            'y': 18,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 9,
                                            'y': 16,
                                            'x': 9,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 22,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'histogram',
                                    'showinput': False,
                                    'autorange': False,
                                    'nbins': 30,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.catalytic.reactivity.reactants.gas_concentration_in',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 9,
                                            'y': 13,
                                            'x': 9,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 9,
                                            'y': 13,
                                            'x': 9,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 9,
                                            'y': 14,
                                            'x': 9,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 9,
                                            'y': 13,
                                            'x': 9,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 16,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'histogram',
                                    'showinput': False,
                                    'autorange': False,
                                    'nbins': 30,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.catalytic.reactivity.pressure',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 9,
                                            'y': 16,
                                            'x': 9,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 9,
                                            'y': 17,
                                            'x': 9,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 9,
                                            'y': 14,
                                            'x': 9,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 9,
                                            'y': 16,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 16,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'histogram',
                                    'showinput': False,
                                    'autorange': False,
                                    'nbins': 30,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.catalytic.reactivity.products.selectivity',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 19,
                                            'x': 0,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 9,
                                            'y': 21,
                                            'x': 0,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 9,
                                            'y': 26,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 9,
                                            'y': 22,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 33,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'histogram',
                                    'showinput': False,
                                    'autorange': False,
                                    'nbins': 30,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.catalytic.reactivity.reactants.conversion',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 22,
                                            'x': 0,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 9,
                                            'y': 25,
                                            'x': 0,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 9,
                                            'y': 22,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 9,
                                            'y': 19,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 30,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'histogram',
                                    'showinput': False,
                                    'autorange': False,
                                    'nbins': 30,
                                    'scale': 'linear',
                                    'quantity': 'results.properties.catalytic.reactivity.rates.reaction_rate',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 25,
                                            'x': 8,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 9,
                                            'y': 29,
                                            'x': 9,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 12,
                                            'y': 30,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 9,
                                            'y': 25,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 36,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'scatterplot',
                                    'autorange': True,
                                    'size': 1000,
                                    'color': 'results.properties.catalytic.catalyst_characterization.surface_area',
                                    'y': 'results.properties.catalytic.reactivity.products.selectivity',
                                    'x': 'results.properties.catalytic.reactivity.reactants.conversion',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 10,
                                            'y': 19,
                                            'x': 8,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 8,
                                            'w': 9,
                                            'y': 21,
                                            'x': 9,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 8,
                                            'w': 9,
                                            'y': 22,
                                            'x': 9,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 9,
                                            'y': 19,
                                            'x': 9,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 8,
                                            'y': 25,
                                            'x': 9,
                                        },
                                    },
                                },
                                {
                                    'type': 'histogram',
                                    'showinput': False,
                                    'autorange': False,
                                    'nbins': 30,
                                    'scale': '1/4',
                                    'quantity': 'results.properties.catalytic.catalyst_characterization.surface_area',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 25,
                                            'x': 0,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 9,
                                            'y': 29,
                                            'x': 0,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 4,
                                            'w': 12,
                                            'y': 34,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 9,
                                            'y': 28,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 8,
                                            'h': 3,
                                            'w': 8,
                                            'y': 39,
                                            'x': 0,
                                        },
                                    },
                                },
                            ]
                        },
                        'columns': {
                            'selected': [
                                'entry_name',
                                'results.properties.catalytic.reactivity.reaction_name',
                                'results.properties.catalytic.catalyst_synthesis.catalyst_type',
                                'results.properties.catalytic.catalyst_synthesis.preparation_method',
                                'results.properties.catalytic.catalyst_characterization.surface_area',
                            ],
                            'options': {
                                'results.material.elements': {
                                    'label': 'Elements',
                                    'align': 'left',
                                },
                                'results.properties.catalytic.catalyst_synthesis.catalyst_type': {
                                    'label': 'Catalyst Type',
                                    'align': 'left',
                                },
                                'results.properties.catalytic.catalyst_synthesis.preparation_method': {
                                    'label': 'Preparation',
                                    'align': 'left',
                                },
                                'results.properties.catalytic.catalyst_characterization.surface_area': {
                                    'label': 'Surface Area (m^2/g)',
                                    'format': {'decimals': 2, 'mode': 'standard'},
                                },
                                'results.properties.catalytic.reactivity.reaction_name': {
                                    'label': 'Reaction Name',
                                    'align': 'left',
                                },
                                'results.properties.catalytic.reactivity.reaction_class': {
                                    'label': 'Reaction Class',
                                    'align': 'left',
                                },
                                'results.properties.catalytic.catalyst_synthesis.catalyst_name': {
                                    'label': 'Catalyst Name',
                                    'align': 'left',
                                },
                                'results.properties.catalytic.reactivity.reactants.name': {
                                    'label': 'Reactants',
                                    'align': 'left',
                                },
                                'results.properties.catalytic.reactivity.products.name': {
                                    'label': 'Products',
                                    'align': 'left',
                                },
                                'references': {'label': 'References', 'align': 'left'},
                                'results.material.chemical_formula_hill': {
                                    'label': 'Formula',
                                    'align': 'left',
                                },
                                'results.material.structural_type': {
                                    'label': 'Dimensionality'
                                },
                                'results.eln.lab_ids': {'label': 'Lab IDs'},
                                'results.eln.sections': {'label': 'Sections'},
                                'results.eln.methods': {'label': 'Methods'},
                                'results.eln.tags': {'label': 'Tags'},
                                'results.eln.instruments': {'label': 'Instruments'},
                                'entry_name': {'label': 'Name', 'align': 'left'},
                                'entry_type': {'label': 'Entry type', 'align': 'left'},
                                'mainfile': {'label': 'Mainfile', 'align': 'left'},
                                'upload_create_time': {
                                    'label': 'Upload time',
                                    'align': 'left',
                                },
                                'authors': {'label': 'Authors', 'align': 'left'},
                                'comment': {'label': 'Comment', 'align': 'left'},
                                'datasets': {'label': 'Datasets', 'align': 'left'},
                                'published': {'label': 'Access'},
                            },
                        },
                        'filter_menus': {
                            'options': {
                                'material': {'label': 'Catalyst Material', 'level': 0},
                                'elements': {
                                    'label': 'Elements / Formula',
                                    'level': 1,
                                    'size': 'xl',
                                },
                                'structure': {
                                    'label': 'Structure / Symmetry',
                                    'level': 1,
                                },
                                'heterogeneouscatalyst': {
                                    'label': 'Catalytic Properties',
                                    'level': 0,
                                },
                                'eln': {'label': 'Electronic Lab Notebook', 'level': 0},
                                'custom_quantities': {
                                    'label': 'User Defined Quantities',
                                    'level': 0,
                                    'size': 'l',
                                },
                                'author': {
                                    'label': 'Author / Origin / Dataset',
                                    'level': 0,
                                    'size': 'm',
                                },
                                'metadata': {
                                    'label': 'Visibility / IDs / Schema',
                                    'level': 0,
                                },
                                'optimade': {
                                    'label': 'Optimade',
                                    'level': 0,
                                    'size': 'm',
                                },
                            }
                        },
                        'filters_locked': {
                            'quantities': 'results.properties.catalytic'
                        },
                        'search_syntaxes': {'exclude': ['free_text']},
                    },
                    'mofs': {
                        'label': 'Metal-Organic Frameworks',
                        'path': 'mofs',
                        'category': 'Use Cases',
                        'description': 'Search metal-organic frameworks (MOFs)',
                        'readme': inspect.cleandoc(
                            r"""
                        This page allows you to search **metal-organic framework
                        (MOF) data** within NOMAD. The filter menu on the left
                        and the shown default columns are specifically designed
                        for MOF exploration. The dashboard directly shows useful
                        interactive statistics about the data.
                    """
                        ),
                        'dashboard': {
                            'widgets': [
                                {
                                    'scale': 'linear',
                                    'quantity': 'results.material.elements',
                                    'type': 'periodictable',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 10,
                                            'w': 25,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 9,
                                            'w': 19,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 9,
                                            'w': 15,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 8,
                                            'w': 11,
                                            'y': 0,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 9,
                                            'y': 0,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'terms',
                                    'scale': 'linear',
                                    'quantity': 'results.material.topology.sbu_type',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 10,
                                            'w': 11,
                                            'y': 0,
                                            'x': 25,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 9,
                                            'w': 11,
                                            'y': 0,
                                            'x': 19,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 9,
                                            'w': 9,
                                            'y': 0,
                                            'x': 15,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 8,
                                            'w': 7,
                                            'y': 0,
                                            'x': 11,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 3,
                                            'y': 0,
                                            'x': 9,
                                        },
                                    },
                                },
                                {
                                    'type': 'histogram',
                                    'autorange': 'false',
                                    'showinput': 'true',
                                    'nbins': 30,
                                    'scale': 'linear',
                                    'quantity': 'results.material.topology.pore_limiting_diameter',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 19,
                                            'y': 10,
                                            'x': 0,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 15,
                                            'y': 9,
                                            'x': 0,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 12,
                                            'y': 9,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 9,
                                            'y': 8,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 3,
                                            'w': 6,
                                            'y': 6,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'histogram',
                                    'autorange': 'false',
                                    'nbins': 30,
                                    'scale': 'linear',
                                    'quantity': 'results.material.topology.largest_cavity_diameter',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 17,
                                            'y': 10,
                                            'x': 19,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 15,
                                            'y': 14,
                                            'x': 0,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 12,
                                            'y': 14,
                                            'x': 0,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 9,
                                            'y': 8,
                                            'x': 9,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 3,
                                            'w': 6,
                                            'y': 6,
                                            'x': 6,
                                        },
                                    },
                                },
                                {
                                    'type': 'histogram',
                                    'autorange': 'false',
                                    'nbins': 30,
                                    'scale': 'linear',
                                    'quantity': 'results.material.topology.accessible_surface_area',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 19,
                                            'y': 16,
                                            'x': 0,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 15,
                                            'y': 9,
                                            'x': 15,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 12,
                                            'y': 9,
                                            'x': 11,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 9,
                                            'y': 12,
                                            'x': 0,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 3,
                                            'w': 6,
                                            'y': 9,
                                            'x': 0,
                                        },
                                    },
                                },
                                {
                                    'type': 'histogram',
                                    'autorange': 'false',
                                    'nbins': 30,
                                    'scale': 'linear',
                                    'quantity': 'results.material.topology.void_fraction',
                                    'layout': {
                                        'xxl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 6,
                                            'w': 17,
                                            'y': 16,
                                            'x': 19,
                                        },
                                        'xl': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 15,
                                            'y': 14,
                                            'x': 15,
                                        },
                                        'lg': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 5,
                                            'w': 12,
                                            'y': 14,
                                            'x': 11,
                                        },
                                        'md': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 4,
                                            'w': 9,
                                            'y': 12,
                                            'x': 9,
                                        },
                                        'sm': {
                                            'minH': 3,
                                            'minW': 3,
                                            'h': 3,
                                            'w': 6,
                                            'y': 9,
                                            'x': 6,
                                        },
                                    },
                                },
                            ]
                        },
                        'columns': {
                            'selected': [
                                'results.material.chemical_formula_iupac',
                                'mainfile',
                                'authors',
                            ],
                            'options': {
                                'results.material.chemical_formula_iupac': {
                                    'label': 'Formula',
                                    'align': 'left',
                                },
                                'mainfile': {'label': 'Mainfile', 'align': 'left'},
                                'upload_create_time': {
                                    'label': 'Upload time',
                                    'align': 'left',
                                },
                                'authors': {'label': 'Authors', 'align': 'left'},
                                'comment': {'label': 'Comment', 'align': 'left'},
                                'datasets': {'label': 'Datasets', 'align': 'left'},
                                'published': {'label': 'Access'},
                            },
                        },
                        'filter_menus': {
                            'options': {
                                'material': {'label': 'Material', 'level': 0},
                                'elements': {
                                    'label': 'Elements / Formula',
                                    'level': 1,
                                    'size': 'xl',
                                },
                                'structure': {'label': 'Structure', 'level': 1},
                                'electronic': {
                                    'label': 'Electronic Properties',
                                    'level': 0,
                                },
                                'author': {
                                    'label': 'Author / Origin / Dataset',
                                    'level': 0,
                                    'size': 'm',
                                },
                                'metadata': {
                                    'label': 'Visibility / IDs / Schema',
                                    'level': 0,
                                },
                                'optimade': {
                                    'label': 'Optimade',
                                    'level': 0,
                                    'size': 'm',
                                },
                            }
                        },
                        'filters_locked': {'results.material.topology.label': 'MOF'},
                        'search_syntaxes': {'exclude': ['free_text']},
                    },
                },
            }
        ),
        description='Contains the App definitions.',
    )
    north: NORTHUI = Field(
        NORTHUI(), description='NORTH (NOMAD Remote Tools Hub) UI configuration.'
    )
    example_uploads: ExampleUploads = Field(
        ExampleUploads(), description='Controls the available example uploads.'
    )
