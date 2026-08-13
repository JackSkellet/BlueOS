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
          Services and connectivity
        </div>
        <div class="text-caption text--secondary">
          Stage any number of changes, then apply them with one Core restart
        </div>
      </div>
    </v-card-title>
    <v-divider />
    <v-card-text>
      <v-alert v-if="operation_error" type="error" dense text>
        {{ operation_error }}
      </v-alert>
      <v-alert v-if="restarting_core" type="info" dense text>
        BlueOS Core is restarting to apply your changes. This page will reload automatically.
      </v-alert>
      <v-alert v-else-if="has_changes" type="info" dense text>
        Your changes are staged. Nothing will restart until you select Apply and restart.
      </v-alert>
      <v-alert v-if="!wifi_enabled" type="warning" dense text>
        Disabling onboard Wi-Fi disconnects every client using that radio.
      </v-alert>
      <v-alert v-if="client_internet_enabled" type="warning" dense text>
        Topside Internet uses the connected browser computer as BlueOS's gateway. Internet sharing must be enabled
        on that computer.
      </v-alert>
      <v-progress-linear v-if="loading_states" indeterminate color="primary" class="mb-3" />

      <div v-for="(setting, index) in settings" :key="setting.identifier">
        <div
          v-if="index === 0 || settings[index - 1].category !== setting.category"
          class="text-overline text--secondary mb-3"
          :class="{ 'mt-5': index > 0 }"
        >
          {{ setting.category }}
        </div>
        <v-row align="center" no-gutters>
          <v-col cols="12" sm="8">
            <div class="d-flex align-center">
              <v-avatar :color="setting.enabled ? setting.color : 'grey'" size="48" class="mr-4">
                <v-icon color="white" size="28">
                  {{ setting.icon }}
                </v-icon>
              </v-avatar>
              <div>
                <div class="d-flex align-center flex-wrap">
                  <span class="text-subtitle-1 font-weight-medium mr-2">{{ setting.name }}</span>
                  <v-chip
                    x-small
                    :color="setting.available ? (setting.enabled ? 'success' : 'grey') : 'warning'"
                    text-color="white"
                  >
                    {{ setting.available ? (setting.enabled ? 'Enabled' : 'Disabled') : 'Not installed' }}
                  </v-chip>
                </div>
                <div class="text-caption text--secondary">
                  {{ setting.description }}
                </div>
              </div>
            </div>
          </v-col>
          <v-col cols="12" sm="4" class="d-flex justify-sm-end mt-3 mt-sm-0">
            <v-switch
              v-tooltip="`${setting.enabled ? 'Disable' : 'Enable'} ${setting.name}`"
              :input-value="setting.enabled"
              :label="setting.enabled ? 'Enabled' : 'Disabled'"
              :color="setting.color"
              :disabled="loading_states || applying_changes || restarting_core || !setting.available"
              hide-details
              inset
              class="mt-0"
              @change="setSettingState(setting.identifier, $event)"
            />
          </v-col>
        </v-row>
        <v-divider v-if="index < settings.length - 1" class="my-4" />
      </div>

      <div class="d-flex justify-end mt-6">
        <v-btn
          text
          class="mr-2"
          :disabled="!has_changes || applying_changes || restarting_core"
          @click="resetDraft"
        >
          Discard
        </v-btn>
        <v-btn
          color="primary"
          :loading="applying_changes"
          :disabled="!has_changes || loading_states || restarting_core"
          @click="applyChanges"
        >
          <v-icon left>
            mdi-restart
          </v-icon>
          Apply and restart
        </v-btn>
      </div>
    </v-card-text>
  </v-card>
</template>

<script lang="ts">
import Vue from 'vue'

import kraken from '@/components/kraken/KrakenManager'
import { OneMoreTime } from '@/one-more-time'
import commander, { ManagedServiceStates } from '@/store/commander'
import back_axios from '@/utils/api'

const MAJOR_TOM_EXTENSION_IDENTIFIER = 'blueos.major_tom'

type SettingIdentifier = 'ping' | 'cloud' | 'recorder' | 'video' | 'wifi' | 'bluetooth' | 'client_internet'

interface SettingsSnapshot extends ManagedServiceStates {
  cloud: boolean
}

interface SettingDisplay {
  identifier: SettingIdentifier
  category: 'Optional services' | 'Connectivity'
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
      video_enabled: true,
      cloud_enabled: false,
      cloud_available: false,
      cloud_tag: '',
      wifi_enabled: true,
      bluetooth_enabled: true,
      client_internet_enabled: false,
      original_states: null as SettingsSnapshot | null,
      loading_states: true,
      applying_changes: false,
      operation_error: null as string | null,
      restarting_core: false,
      core_went_offline: false,
      restart_poll_task: new OneMoreTime({
        delay: 2000,
        errorDelay: 1000,
        disposeWith: this,
        autostart: false,
      }),
    }
  },

  computed: {
    settings(): SettingDisplay[] {
      return [
        {
          identifier: 'ping',
          category: 'Optional services',
          name: 'Ping Devices',
          description: 'Discovers and connects Blue Robotics Ping sonar devices',
          icon: 'mdi-access-point',
          color: 'primary',
          enabled: this.ping_enabled,
          available: true,
        },
        {
          identifier: 'cloud',
          category: 'Optional services',
          name: 'BlueOS Cloud',
          description: 'Provides Major Tom cloud connectivity and file synchronization',
          icon: 'mdi-cloud',
          color: 'info',
          enabled: this.cloud_enabled,
          available: this.cloud_available,
        },
        {
          identifier: 'recorder',
          category: 'Optional services',
          name: 'BlueOS Recorder',
          description: 'Records BlueOS data to persistent storage',
          icon: 'mdi-record-rec',
          color: 'error',
          enabled: this.recorder_enabled,
          available: true,
        },
        {
          identifier: 'video',
          category: 'Optional services',
          name: 'MAVLink Camera Manager',
          description: 'Manages video streams, cameras, and recording endpoints',
          icon: 'mdi-video',
          color: 'purple',
          enabled: this.video_enabled,
          available: true,
        },
        {
          identifier: 'wifi',
          category: 'Connectivity',
          name: 'Onboard Wi-Fi',
          description: 'Controls the Raspberry Pi Wi-Fi radio',
          icon: 'mdi-wifi',
          color: 'primary',
          enabled: this.wifi_enabled,
          available: true,
        },
        {
          identifier: 'bluetooth',
          category: 'Connectivity',
          name: 'Onboard Bluetooth',
          description: 'Controls the Raspberry Pi Bluetooth radio',
          icon: 'mdi-bluetooth',
          color: 'primary',
          enabled: this.bluetooth_enabled,
          available: true,
        },
        {
          identifier: 'client_internet',
          category: 'Connectivity',
          name: 'Topside Internet',
          description: 'Routes BlueOS Internet traffic through the connected topside computer',
          icon: 'mdi-lan-connect',
          color: 'success',
          enabled: this.client_internet_enabled,
          available: true,
        },
      ]
    },

    has_changes(): boolean {
      const original = this.original_states
      return original !== null
        && (
          original.ping !== this.ping_enabled
          || original.cloud !== this.cloud_enabled
          || original.recorder !== this.recorder_enabled
          || original.video !== this.video_enabled
          || original.wifi !== this.wifi_enabled
          || original.bluetooth !== this.bluetooth_enabled
          || original.client_internet !== this.client_internet_enabled
        )
    },
  },

  mounted() {
    this.restart_poll_task.setAction(async () => {
      try {
        await back_axios({
          method: 'get',
          url: '/helper/latest/web_services',
          timeout: 3000,
        })
        if (this.core_went_offline) {
          this.restart_poll_task.stop()
          window.location.reload()
        }
      } catch (error) {
        this.core_went_offline = true
        throw error
      }
    })
    this.loadServiceStates()
  },

  methods: {
    currentSettings(): SettingsSnapshot {
      return {
        bluetooth: this.bluetooth_enabled,
        client_internet: this.client_internet_enabled,
        cloud: this.cloud_enabled,
        ping: this.ping_enabled,
        recorder: this.recorder_enabled,
        video: this.video_enabled,
        wifi: this.wifi_enabled,
      }
    },

    async loadServiceStates(): Promise<void> {
      this.loading_states = true
      this.operation_error = null
      try {
        const [core_response, installed_extensions] = await Promise.all([
          commander.loadManagedServiceStates(),
          kraken.getInstalledExtensions(),
        ])
        this.bluetooth_enabled = core_response.bluetooth
        this.client_internet_enabled = core_response.client_internet
        this.ping_enabled = core_response.ping
        this.recorder_enabled = core_response.recorder
        this.video_enabled = core_response.video
        this.wifi_enabled = core_response.wifi

        const cloud = installed_extensions.find(
          (extension) => extension.identifier === MAJOR_TOM_EXTENSION_IDENTIFIER,
        )
        this.cloud_available = cloud !== undefined
        this.cloud_enabled = cloud?.enabled ?? false
        this.cloud_tag = cloud?.tag ?? ''
        this.original_states = this.currentSettings()
      } catch (error) {
        this.operation_error = `Unable to load settings: ${String(error)}`
      } finally {
        this.loading_states = false
      }
    },

    setSettingState(setting: SettingIdentifier, enabled: boolean): void {
      if (setting === 'ping') this.ping_enabled = enabled
      if (setting === 'cloud') this.cloud_enabled = enabled
      if (setting === 'recorder') this.recorder_enabled = enabled
      if (setting === 'video') this.video_enabled = enabled
      if (setting === 'wifi') this.wifi_enabled = enabled
      if (setting === 'bluetooth') this.bluetooth_enabled = enabled
      if (setting === 'client_internet') this.client_internet_enabled = enabled
    },

    resetDraft(): void {
      const original = this.original_states
      if (original === null) return
      this.bluetooth_enabled = original.bluetooth
      this.client_internet_enabled = original.client_internet
      this.cloud_enabled = original.cloud
      this.ping_enabled = original.ping
      this.recorder_enabled = original.recorder
      this.video_enabled = original.video
      this.wifi_enabled = original.wifi
    },

    async setCloudService(enabled: boolean): Promise<void> {
      if (!this.cloud_available || !this.cloud_tag) {
        throw new Error('Major Tom is not installed')
      }
      if (enabled) {
        await kraken.enableExtension(MAJOR_TOM_EXTENSION_IDENTIFIER, this.cloud_tag)
      } else {
        await kraken.disableExtension(MAJOR_TOM_EXTENSION_IDENTIFIER)
      }
    },

    async applyChanges(): Promise<void> {
      const original = this.original_states
      if (original === null || !this.has_changes) return

      this.operation_error = null
      this.applying_changes = true
      try {
        if (original.cloud !== this.cloud_enabled) {
          await this.setCloudService(this.cloud_enabled)
        }

        const states: ManagedServiceStates = {
          bluetooth: this.bluetooth_enabled,
          client_internet: this.client_internet_enabled,
          ping: this.ping_enabled,
          recorder: this.recorder_enabled,
          video: this.video_enabled,
          wifi: this.wifi_enabled,
        }
        await back_axios({
          method: 'put',
          url: `${commander.API_URL}/services/enabled`,
          data: states,
          timeout: 10000,
        })
        commander.setManagedServiceStates(states)
        this.original_states = this.currentSettings()
        this.restarting_core = true
        this.core_went_offline = false
        this.restart_poll_task.start()
      } catch (error) {
        this.operation_error = `Unable to apply settings: ${String(error)}`
      } finally {
        this.applying_changes = false
      }
    },
  },
})
</script>
