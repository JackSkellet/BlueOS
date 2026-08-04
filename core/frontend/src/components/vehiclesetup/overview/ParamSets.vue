<template>
  <v-row class="main-container">
    <v-card
      v-if="settings.is_pirate_mode"
      class="card-container"
    >
      <v-card-title class="align-center">
        Reset Parameters to Firmware Defaults
      </v-card-title>
      <v-card-text>
        <p>
          This will effectively wipe your "eeprom". You will lose all your parameters, vehicle setup, and calibrations.
          Use this if you don't know which parameters you changed and need a clean start.
        </p>
      </v-card-text>
      <v-card-actions>
        <v-btn :disabled="wipe_successful" :loading="erasing" color="error" @click="show_warning = true">
          <v-icon left>
            mdi-skull-crossbones
          </v-icon>
          Reset All Parameters
        </v-btn>
        <v-btn
          v-if="wipe_successful && !done"
          color="warning"
          :loading="rebooting"
          @click="restartAutopilot"
        >
          Reboot Autopilot
        </v-btn>
        <v-alert
          v-if="wipe_successful"
          dense
          text
          type="success"
        >
          Parameters reset <b>successful</b>. <span v-if="!done"> Please reboot the vehicle to apply changes. </span>
        </v-alert>
      </v-card-actions>
    </v-card>
    <v-card class="card-container">
      <v-card-title class="align-center">
        Load Recommended Parameter sets
      </v-card-title>
      <v-card-text>
        <p>
          These are the recommended parameter sets for your vehicle and firmware version. Curated by Blue Robotics
        </p>
      </v-card-text>
      <v-card-actions>
        <v-btn
          v-for="(paramSet, name) in filtered_param_sets"
          :key="name"
          color="primary"
          @click="loadParams(name, paramSet)"
        >
          {{ name.split('/').pop() }}
        </v-btn>
        <p v-if="(Object.keys(filtered_param_sets).length === 0)">
          No parameters available for this setup
        </p>
      </v-card-actions>
    </v-card>
    <v-card class="card-container">
      <v-card-title class="align-center">
        Parameter Profiles
      </v-card-title>
      <v-card-text>
        <p>Back up the current vehicle setup or upload parameter files for quick reuse.</p>
        <v-alert v-if="profile_error" type="error" dense text>
          {{ profile_error }}
        </v-alert>
        <div class="d-flex align-center flex-wrap">
          <v-btn
            v-tooltip="'Save the current vehicle parameters as a profile'"
            color="primary"
            :disabled="!parameters_finished_loading"
            :loading="saving_profile"
            @click="backupCurrentParameters"
          >
            <v-icon left>
              mdi-content-save
            </v-icon>
            Back up current parameters
          </v-btn>
          <v-file-input
            v-model="profile_files"
            accept=".params,.parm,.param"
            class="profile-file-input"
            dense
            multiple
            outlined
            prepend-icon="mdi-file-upload"
            label="Upload parameter files"
            :disabled="saving_profile"
            @change="uploadParameterFiles"
          />
        </div>
        <v-progress-linear v-if="loading_profiles" indeterminate color="primary" />
        <v-list v-else-if="profiles.length" two-line>
          <v-list-item v-for="profile in profiles" :key="profile.id">
            <v-list-item-content>
              <v-list-item-title>{{ profile.name }}</v-list-item-title>
              <v-list-item-subtitle>
                {{ Object.keys(profile.parameters).length }} parameters
              </v-list-item-subtitle>
            </v-list-item-content>
            <v-list-item-action class="profile-actions">
              <v-btn color="primary" small @click="loadParams(profile.name, profile.parameters)">
                <v-icon left small>
                  mdi-upload
                </v-icon>
                Load and apply
              </v-btn>
              <v-btn v-tooltip="'Edit profile name'" small outlined @click="startRenamingProfile(profile)">
                <v-icon left small>
                  mdi-pencil
                </v-icon>
                Edit name
              </v-btn>
              <v-btn color="error" small outlined @click="profile_to_delete = profile">
                <v-icon left small>
                  mdi-delete
                </v-icon>
                Delete item
              </v-btn>
            </v-list-item-action>
          </v-list-item>
        </v-list>
        <p v-else class="text--secondary mb-0">
          No parameter profiles saved yet.
        </p>
      </v-card-text>
    </v-card>
    <ParameterLoader
      v-if="selected_paramset"
      :parameters="selected_paramset"
      @done="selected_paramset = {}"
    />

    <WarningDialog
      v-model="show_warning"
      :message="warningMessage"
      confirm-label="Yes, reset them"
      @confirm="wipe"
    />
    <WarningDialog
      :value="profile_to_delete !== undefined"
      :message="`Delete parameter profile '${profile_to_delete?.name ?? ''}'?`"
      confirm-label="Delete item"
      @input="profile_to_delete = undefined"
      @confirm="deleteProfile"
    />
    <v-dialog v-model="rename_profile_dialog" max-width="500px">
      <v-card>
        <v-card-title>Edit profile name</v-card-title>
        <v-card-text>
          <v-text-field v-model="profile_name" autofocus label="Profile name" @keyup.enter="renameProfile" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn text @click="rename_profile_dialog = false">
            Cancel
          </v-btn>
          <v-btn color="primary" :disabled="!profile_name.trim()" @click="renameProfile">
            Save name
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-row>
</template>

<script lang="ts">
import { format } from 'date-fns'
import { SemVer } from 'semver'
import Vue from 'vue'

import * as AutopilotManager from '@/components/autopilot/AutopilotManagerUpdater'
import { fetchCurrentBoard } from '@/components/autopilot/AutopilotManagerUpdater'
import WarningDialog from '@/components/common/WarningDialog.vue'
import ParameterLoader from '@/components/parameter-editor/ParameterLoader.vue'
import mavlink2rest from '@/libs/MAVLink2Rest'
import {
  MavCmd, MavResult,
} from '@/libs/MAVLink2Rest/mavlink2rest-ts/messages/mavlink2rest-enum'
import Notifier from '@/libs/notifier'
import { fetchParamSets, paramSetsForFirmware } from '@/libs/parameter_repository'
import settings from '@/libs/settings'
import autopilot_data from '@/store/autopilot'
import autopilot from '@/store/autopilot_manager'
import commander from '@/store/commander'
import Parameter from '@/types/autopilot/parameter'
import { Dictionary } from '@/types/common'
import { frontend_service } from '@/types/frontend_services'
import back_axios from '@/utils/api'

const notifier = new Notifier(frontend_service)

interface ParameterProfile {
  id: string
  name: string
  parameters: Dictionary<number>
}

export default Vue.extend({
  name: 'ParamSets',
  components: {
    ParameterLoader,
    WarningDialog,
  },
  data: () => ({
    all_param_sets: {} as Dictionary<Dictionary<number>>,
    selected_paramset: {} as Dictionary<number>,
    selected_paramset_name: undefined as (undefined | string),
    wipe_successful: false,
    rebooting: false,
    done: false,
    erasing: false,
    settings,
    show_warning: false,
    profiles: [] as ParameterProfile[],
    profile_files: [] as File[],
    loading_profiles: true,
    saving_profile: false,
    profile_error: null as string | null,
    profile_to_delete: undefined as ParameterProfile | undefined,
    profile_to_rename: undefined as ParameterProfile | undefined,
    profile_name: '',
    rename_profile_dialog: false,
  }),
  computed: {
    vehicle(): string | null {
      return autopilot.firmware_vehicle_type
    },
    version(): SemVer | null {
      return autopilot.firmware_info?.version ?? null
    },
    filtered_param_sets(): Dictionary<Dictionary<number>> {
      return paramSetsForFirmware(this.all_param_sets, this.vehicle, this.version, autopilot.current_board)
    },
    warningMessage(): string {
      return 'You will lose ALL your parameters, vehicle setup, and calibrations. Are you sure you want to reset?'
    },
    parameters_finished_loading(): boolean {
      return autopilot_data.finished_loading
    },
  },
  mounted() {
    fetchCurrentBoard()
    this.loadParamSets()
    this.loadProfiles()
  },
  methods: {
    async loadParamSets() {
      try {
        this.all_param_sets = await fetchParamSets()
      } catch (error) {
        notifier.pushError('PARAM_SETS_FETCH_FAIL', error)
      }
    },
    async loadParams(name: string, paramset: Dictionary<number>) {
      this.selected_paramset_name = name
      this.selected_paramset = paramset
    },
    async loadProfiles(): Promise<void> {
      this.loading_profiles = true
      this.profile_error = null
      try {
        const response = await back_axios.get(`${commander.API_URL}/parameter_profiles`)
        this.profiles = response.data
      } catch (error) {
        this.profile_error = `Unable to load parameter profiles: ${String(error)}`
      } finally {
        this.loading_profiles = false
      }
    },
    currentParameters(): Dictionary<number> {
      return Object.fromEntries(
        autopilot_data.parameters
          .filter((parameter: Parameter) => !parameter.readonly)
          .map((parameter: Parameter) => [parameter.name, parameter.value]),
      )
    },
    async backupCurrentParameters(): Promise<void> {
      const name = `Current parameters ${format(new Date(), 'yyyy-MM-dd HH:mm')}`
      await this.saveProfile(name, this.currentParameters())
    },
    async saveProfile(name: string, parameters: Dictionary<number>): Promise<void> {
      this.saving_profile = true
      this.profile_error = null
      try {
        await back_axios.post(`${commander.API_URL}/parameter_profiles`, parameters, { params: { name } })
        await this.loadProfiles()
      } catch (error) {
        this.profile_error = `Unable to save parameter profile: ${String(error)}`
      } finally {
        this.saving_profile = false
      }
    },
    parseParameterFile(content: string): Dictionary<number> {
      const parameters: Dictionary<number> = {}
      const formats = [
        /^\S+\s+\S+\s+(\S+)\s+(\S+)/,
        /^([^,]+)\s*,\s*([^,]+)/,
        /^(\S+)\s+(\S+)/,
      ]

      content.split(/\r?\n/).forEach((line) => {
        const trimmed_line = line.trim()
        if (!trimmed_line || trimmed_line.startsWith('#')) return
        const match = formats.map((pattern) => trimmed_line.match(pattern)).find((result) => result !== null)
        if (!match) return
        const value = Number.parseFloat(match[2])
        if (!Number.isNaN(value)) parameters[match[1].trim()] = value
      })
      return parameters
    },
    async uploadParameterFiles(files: File[] | File | null): Promise<void> {
      let selected_files: File[] = []
      if (Array.isArray(files)) {
        selected_files = files
      } else if (files) {
        selected_files = [files]
      }
      if (!selected_files.length) return

      for (const file of selected_files) {
        const parameters = this.parseParameterFile(await file.text())
        if (!Object.keys(parameters).length) {
          this.profile_error = `${file.name} does not contain any valid parameters.`
          continue
        }
        await this.saveProfile(file.name.replace(/\.(params?|parm)$/i, ''), parameters)
      }
      this.profile_files = []
    },
    startRenamingProfile(profile: ParameterProfile): void {
      this.profile_to_rename = profile
      this.profile_name = profile.name
      this.rename_profile_dialog = true
    },
    async renameProfile(): Promise<void> {
      if (!this.profile_to_rename || !this.profile_name.trim()) return
      this.profile_error = null
      try {
        await back_axios.put(`${commander.API_URL}/parameter_profiles/${this.profile_to_rename.id}`, undefined, {
          params: { name: this.profile_name },
        })
        this.rename_profile_dialog = false
        await this.loadProfiles()
      } catch (error) {
        this.profile_error = `Unable to rename parameter profile: ${String(error)}`
      }
    },
    async deleteProfile(): Promise<void> {
      if (!this.profile_to_delete) return
      this.profile_error = null
      try {
        await back_axios.delete(`${commander.API_URL}/parameter_profiles/${this.profile_to_delete.id}`)
        this.profile_to_delete = undefined
        await this.loadProfiles()
      } catch (error) {
        this.profile_error = `Unable to delete parameter profile: ${String(error)}`
      }
    },
    async restartAutopilot(): Promise<void> {
      this.rebooting = true
      await AutopilotManager.restart()
      autopilot_data.reset()
      // reset to initial
      this.done = true
      this.rebooting = false
    },
    async wipe() {
      this.erasing = true
      mavlink2rest.sendCommandLong(
        MavCmd.MAV_CMD_PREFLIGHT_STORAGE,
        2, // PARAM_RESET_CONFIG_DEFAULT from MAV_CMD_PREFLIGHT_STORAGE
      )
      const timeout = 0
      try {
        const ack = await mavlink2rest.waitForAck(MavCmd.MAV_CMD_PREFLIGHT_STORAGE)
        if (ack.result.type !== MavResult.MAV_RESULT_ACCEPTED) {
          throw new Error(`Command not accepted: ${ack.result.type}`)
        }
        clearTimeout(timeout)
        this.wipe_successful = true
        autopilot_data.setRebootRequired(true)
      } catch (e) {
        this.wipe_successful = false
        notifier.pushError('PARAM_RESET_FAIL', `Parameters Reset failed: ${e}`, true)
      } finally {
        this.erasing = false
        this.show_warning = false
      }
    },

  },
})
</script>
<style scoped>
button {
    margin: 10px;
}

.main-container {
  display: flex;
  padding: 25px;
  gap: 10px;
}

.card-container {
  flex: 1 1 calc(50% - 10px);
  max-width: calc(50% - 0px);
  min-width: 600px;
}

.profile-file-input {
  max-width: 420px;
  margin: 10px;
}

.profile-actions {
  display: flex;
  flex-direction: row;
  gap: 8px;
}

.virtual-table-row {
  display: flex;
  margin: 0;
  margin-bottom: 15px;
  border-bottom: 1px solid #eee;
}

.virtual-table-cell {
  flex: 1;
  padding: 5px;
  height: 30px;
}
.virtual-table-cell .v-input {
  margin-top: -6px;
}

.checkbox-label label {
  font-weight: 700;
}
</style>
