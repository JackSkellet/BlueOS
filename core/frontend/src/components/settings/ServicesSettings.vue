<template>
  <v-card class="mb-4" elevation="2">
    <v-card-title class="d-flex align-center">
      <v-avatar color="teal" size="36" class="mr-3">
        <v-icon color="white" size="20">
          mdi-server
        </v-icon>
      </v-avatar>
      <div>
        <div class="text-subtitle-1 font-weight-medium">
          Services
        </div>
        <div class="text-caption text--secondary">
          Control optional BlueOS services
        </div>
      </div>
    </v-card-title>
    <v-divider />
    <v-card-text>
      <v-alert v-if="operation_error" type="error" dense text>
        {{ operation_error }}
      </v-alert>
      <v-alert v-if="restarting_core" type="info" dense text>
        BlueOS Core is restarting to apply the service change. This page will reload automatically.
      </v-alert>
      <v-progress-linear v-if="loading_states" indeterminate color="primary" class="mb-3" />

      <div v-for="(service, index) in services" :key="service.identifier">
        <v-row align="center" no-gutters>
          <v-col cols="12" sm="8">
            <div class="d-flex align-center">
              <v-avatar :color="service.enabled ? service.color : 'grey'" size="48" class="mr-4">
                <v-icon color="white" size="28">
                  {{ service.icon }}
                </v-icon>
              </v-avatar>
              <div>
                <div class="d-flex align-center flex-wrap">
                  <span class="text-subtitle-1 font-weight-medium mr-2">{{ service.name }}</span>
                  <v-chip
                    x-small
                    :color="service.available ? (service.enabled ? 'success' : 'grey') : 'warning'"
                    text-color="white"
                  >
                    {{ service.available ? (service.enabled ? 'Enabled' : 'Disabled') : 'Not installed' }}
                  </v-chip>
                </div>
                <div class="text-caption text--secondary">
                  {{ service.description }}
                </div>
              </div>
            </div>
          </v-col>
          <v-col cols="12" sm="4" class="text-sm-right mt-3 mt-sm-0">
            <v-btn
              v-tooltip="`${service.enabled ? 'Disable' : 'Enable'} ${service.name}`"
              outlined
              small
              :color="service.enabled ? 'error' : 'success'"
              :loading="active_service === service.identifier"
              :disabled="loading_states || restarting_core || !service.available || active_service !== null"
              @click="toggleService(service.identifier)"
            >
              <v-icon left small>
                {{ service.enabled ? 'mdi-stop-circle-outline' : 'mdi-play-circle-outline' }}
              </v-icon>
              {{ service.enabled ? 'Disable' : 'Enable' }}
            </v-btn>
          </v-col>
        </v-row>
        <v-divider v-if="index < services.length - 1" class="my-4" />
      </div>

      <div class="text-caption text--secondary mt-4">
        Ping and Recorder changes restart BlueOS Core. Disabled services remain disabled after a reboot.
      </div>
    </v-card-text>
  </v-card>
</template>

<script lang="ts">
import Vue from 'vue'

import kraken from '@/components/kraken/KrakenManager'
import { OneMoreTime } from '@/one-more-time'
import commander from '@/store/commander'
import back_axios from '@/utils/api'

const MAJOR_TOM_EXTENSION_IDENTIFIER = 'blueos.major_tom'

type ServiceIdentifier = 'ping' | 'cloud' | 'recorder'
type CoreServiceIdentifier = Exclude<ServiceIdentifier, 'cloud'>

interface ServiceDisplay {
  identifier: ServiceIdentifier
  name: string
  description: string
  icon: string
  color: string
  enabled: boolean
  available: boolean
}

export default Vue.extend({
  name: 'ServicesSettings',

  data() {
    return {
      ping_enabled: true,
      recorder_enabled: true,
      cloud_enabled: false,
      cloud_available: false,
      cloud_tag: '',
      loading_states: true,
      active_service: null as ServiceIdentifier | null,
      operation_error: null as string | null,
      restarting_core: false,
      restart_poll_task: new OneMoreTime({
        delay: 2000,
        errorDelay: 1000,
        disposeWith: this,
        autostart: false,
      }),
    }
  },

  computed: {
    services(): ServiceDisplay[] {
      return [
        {
          identifier: 'ping',
          name: 'Ping Devices',
          description: 'Discovers and connects Blue Robotics Ping sonar devices',
          icon: 'mdi-access-point',
          color: 'primary',
          enabled: this.ping_enabled,
          available: true,
        },
        {
          identifier: 'cloud',
          name: 'BlueOS Cloud',
          description: 'Provides Major Tom cloud connectivity and file synchronization',
          icon: 'mdi-cloud',
          color: 'info',
          enabled: this.cloud_enabled,
          available: this.cloud_available,
        },
        {
          identifier: 'recorder',
          name: 'BlueOS Recorder',
          description: 'Records BlueOS data to persistent storage',
          icon: 'mdi-record-rec',
          color: 'error',
          enabled: this.recorder_enabled,
          available: true,
        },
      ]
    },
  },

  mounted() {
    this.restart_poll_task.setAction(async () => {
      await back_axios({
        method: 'get',
        url: '/helper/latest/web_services',
        timeout: 3000,
      })
      this.restart_poll_task.stop()
      window.location.reload()
    })
    this.loadServiceStates()
  },

  methods: {
    async loadServiceStates(): Promise<void> {
      this.loading_states = true
      this.operation_error = null
      try {
        const [core_response, installed_extensions] = await Promise.all([
          back_axios({
            method: 'get',
            url: `${commander.API_URL}/services/enabled`,
            timeout: 10000,
          }),
          kraken.getInstalledExtensions(),
        ])
        this.ping_enabled = Boolean(core_response.data?.ping)
        this.recorder_enabled = Boolean(core_response.data?.recorder)

        const cloud = installed_extensions.find(
          (extension) => extension.identifier === MAJOR_TOM_EXTENSION_IDENTIFIER,
        )
        this.cloud_available = cloud !== undefined
        this.cloud_enabled = cloud?.enabled ?? false
        this.cloud_tag = cloud?.tag ?? ''
      } catch (error) {
        this.operation_error = `Unable to load service states: ${String(error)}`
      } finally {
        this.loading_states = false
      }
    },

    async toggleService(service: ServiceIdentifier): Promise<void> {
      this.operation_error = null
      this.active_service = service
      try {
        if (service === 'cloud') {
          await this.toggleCloudService()
          return
        }
        await this.toggleCoreService(service)
      } catch (error) {
        this.operation_error = `Unable to update the service: ${String(error)}`
      } finally {
        if (!this.restarting_core) {
          this.active_service = null
        }
      }
    },

    async toggleCloudService(): Promise<void> {
      if (!this.cloud_available || !this.cloud_tag) {
        throw new Error('Major Tom is not installed')
      }

      const enable = !this.cloud_enabled
      if (enable) {
        await kraken.enableExtension(MAJOR_TOM_EXTENSION_IDENTIFIER, this.cloud_tag)
      } else {
        await kraken.disableExtension(MAJOR_TOM_EXTENSION_IDENTIFIER)
      }
      this.cloud_enabled = enable
    },

    async toggleCoreService(service: CoreServiceIdentifier): Promise<void> {
      const enable = service === 'ping' ? !this.ping_enabled : !this.recorder_enabled
      const response = await back_axios({
        method: 'put',
        url: `${commander.API_URL}/services/${service}`,
        params: { enabled: enable },
        timeout: 10000,
      })
      this.ping_enabled = Boolean(response.data?.ping)
      this.recorder_enabled = Boolean(response.data?.recorder)
      this.restarting_core = true

      try {
        await back_axios({
          method: 'post',
          url: '/version-chooser/v1.0/version/restart',
          timeout: 10000,
        })
      } finally {
        this.restart_poll_task.start()
      }
    },
  },
})
</script>
