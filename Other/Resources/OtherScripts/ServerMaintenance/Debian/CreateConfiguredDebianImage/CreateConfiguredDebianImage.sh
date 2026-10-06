#!/bin/bash
set -e
#set -o pipefail

# guide to create image for bios: https://wiki.debian.org/DebianInstaller/Preseed/EditIso
# guide to create image for efi: https://wiki.debian.org/RepackBootableISO

scriptfolder="/Workspace/Data/Clouds/cloud.now327.de/Documents/Machines/SecMachine/Scripts/Other/ScriptCollection/ServerMaintenance/Debian/CreateConfiguredDebianImage"
preseed_template_file="$scriptfolder/preseedTemplate.cfg"
preseed_file="$scriptfolder/preseed.cfg"

isofile=$1
hostname=$2
ssh_public_key=$3
user_password=$4
root_password=$5
locale=$6
keymap=$7
architecture=$8
result_folder=$9
ssh_port="${10}"
disk_size="${11}"
temp_folder="${12}"
# allowed values/formats for disk_size are: "max", "75%" and "250GB"

#-----------------------------------------------------------------------------------------------
echo "Prepare..."
pwd=$PWD
timestamp=$(date +"%Y%m%d%H%M%S")

if [ -d "$temp_folder" ]; then
  chmod -R 777 $temp_folder # without that you get "permission denied" when trying to remove the folder"
  rm -rf $temp_folder
fi
mkdir $temp_folder

isofile_without_extension=${isofile::-4}
iso_filename="$hostname-installer"
hostname_lower="${hostname,,}"
if [ -d "$preseed_file" ] ; then
  rm -f "$preseed_file"
fi

preseed_target_file="$result_folder/${iso_filename}_$timestamp.iso"
if [ -f "$preseed_target_file" ] ; then
  rm -f "$preseed_target_file"
fi

#-----------------------------------------------------------------------------------------------
echo "Generate preseed-file..."
#echo $preseed_template_file
#echo $preseed_file
cp $preseed_template_file $preseed_file
sed -i "s/__\[hostname\]__/$hostname_lower/g" $preseed_file
sed -i "s/__\[ssh_public_key\]__/$ssh_public_key/g" $preseed_file
sed -i "s/__\[user_password\]__/$user_password/g" $preseed_file
sed -i "s/__\[root_password\]__/$root_password/g" $preseed_file
sed -i "s/__\[locale\]__/$locale/g" $preseed_file
sed -i "s/__\[keymap\]__/$keymap/g" $preseed_file
sed -i "s/__\[ssh_port\]__/$ssh_port/g" $preseed_file
sed -i "s/__\[disk_size\]__/$disk_size/g" $preseed_file

echo "preseedfile ($preseed_file):"
#cat "$preseed_file"

#-----------------------------------------------------------------------------------------------

echo "Extract ISO..."

mountpoint="$temp_folder/original"
mkdir -p "$mountpoint"
mount -o loop "$isofile" "$mountpoint"

work_directory="$temp_folder/files"
mkdir "$work_directory"

cp -a "$mountpoint/." "$work_directory/"
umount "$mountpoint"
chmod 777 -R "$work_directory"

#-----------------------------------------------------------------------------------------------
echo "Add Preseed..."

cd $scriptfolder
gunzip $work_directory/install.$architecture/initrd.gz
echo "preseed.cfg" | cpio -H newc -o -A -F $work_directory/install.$architecture/initrd
gzip $work_directory/install.$architecture/initrd
cd -

##-----------------------------------------------------------------------------------------------
echo "Edit boot menu..."

menu_cfg="$work_directory/debian/isolinux/menu.cfg"
txt_cfg="$work_directory/debian/isolinux/txt.cfg"
truncate -s 0 "$menu_cfg"
inhalt="menu hshift 4
width 70
menu title $hostname-Installer
include stdmenu.cfg
include txt.cfg"

echo "$inhalt" > "$menu_cfg"

#echo "menu-cfg:"
#cat $menu_cfg

echo "timeout 20" >> "$txt_cfg"
echo "ontimeout /install.amd/vmlinuz vga=788 initrd=/install.amd/initrd.gz --- quiet " >> "$txt_cfg"
echo "menu autoboot Auto-install will be started in # second{,s}..." >> "$txt_cfg"
#
##-----------------------------------------------------------------------------------------------
echo "Build new ISO..."
ls -l $work_directory/isolinux/isolinux.bin
#read -p "Press key to continue.. " -n1 -s
cd $work_directory
find -follow -type f ! -name md5sum.txt -print0 | xargs -0 md5sum > md5sum.txt
cd -

ISOLINUX_MBR="/usr/lib/ISOLINUX/isohdpfx.bin"
#genisoimage -r -J -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -o $preseed_target_file $work_directory
xorriso -as mkisofs \
  -r -J \
  -b isolinux/isolinux.bin \
  -c isolinux/boot.cat \
  -no-emul-boot -boot-load-size 4 -boot-info-table \
  -eltorito-alt-boot \
  -e boot/grub/efi.img \
  -no-emul-boot \
  -isohybrid-mbr /usr/lib/ISOLINUX/isohdpfx.bin \
  -o "$preseed_target_file" "$work_directory"
ls -la $preseed_target_file
chown $SUDO_USER:$SUDO_USER $preseed_target_file

#-----------------------------------------------------------------------------------------------
echo "Create test-environment..."

test_disk="/tmp/testdisk.qcow2"
if [ -f "$test_disk" ] ; then
    rm "$test_disk"
fi
qemu-img create -f qcow2 $test_disk 10G
chown $SUDO_USER:$SUDO_USER $test_disk

#-----------------------------------------------------------------------------------------------
echo "Cleanup..."
rm $preseed_file
rm -rf "$temp_folder"

#-----------------------------------------------------------------------------------------------
echo "Checks..."
#isohybrid -v $preseed_target_file
#fdisk -l $preseed_target_file
#isoinfo -i $preseed_target_file -l
#xorriso -indev $preseed_target_file -report_el_torito plain
ls -la $preseed_target_file
#-----------------------------------------------------------------------------------------------
echo "Finish..."
echo "Created ISO: $preseed_target_file"
echo "Testable with the qemu-command 'qemu-system-x86_64 -hda $test_disk -cdrom "$preseed_target_file" -m 1024 -boot d'"
echo "Testable with the kvm-command 'kvm -m 2048 -cdrom $preseed_target_file -boot d'"
echo "✅ Done!"
#new     : /Workspace/Data/OSImages/BaseImages/debian-13.1.0-amd64-netinst.iso
#original: /Workspace/Data/OSImages/SpecialImages/r04-installer.iso

#xorriso -indev /Workspace/Data/OSImages/BaseImages/debian-13.1.0-amd64-netinst.iso -report_el_torito plain
#xorriso -indev /Workspace/Data/OSImages/SpecialImages/r04-installer.iso -report_el_torito plain
#"sudo kvm -m 2048 -cdrom $preseed_target_file -boot d -enable-kvm -smp 2 -net nic -net user"
