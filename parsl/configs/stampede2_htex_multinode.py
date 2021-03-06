from parsl.config import Config
from parsl.providers import SlurmProvider
from parsl.executors import HighThroughputExecutor
from parsl.addresses import address_by_hostname
from parsl.data_provider.scheme import GlobusScheme


config = Config(
    executors=[
        HighThroughputExecutor(
            label='Stampede2_HTEX',
            address=address_by_hostname(),
            provider=SlurmProvider(
                nodes_per_block=2,
                init_blocks=1,
                min_blocks=1,
                partition='YOUR_PARTITION',
                # string to prepend to #SBATCH blocks in the submit
                # script to the scheduler eg: '#SBATCH --constraint=knl,quad,cache'
                scheduler_options='',
                # Command to be run before starting a worker, such as:
                # 'module load Anaconda; source activate parsl_env'.
                worker_init='',
                walltime='00:30:00'
            ),
            storage_access=[GlobusScheme(
                endpoint_uuid='ceea5ca0-89a9-11e7-a97f-22000a92523b',
                endpoint_path='/',
                local_path='/'
            )]
        )

    ],
)
